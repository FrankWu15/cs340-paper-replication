#!/usr/bin/env python3
"""P0 阶段：解析论文 artifact，把三类材料拼成可用的数据表。

输入（--artifact 指向解压出来的 go-concurrency-bugs-master）:
    blocking-bugs/{app}/*.txt       83 个修复补丁
    non-blocking-bugs/{app}/*.txt   86 个修复补丁
    bug table.xlsx                  3 个工作表：application / blocking / non-blocking

输出（--outdir，默认 repro/data）:
    bug_table_application.csv       论文 Table 1 的原始数据（6 个项目）
    bug_table_blocking.csv          85 条阻塞型 bug 标注
    bug_table_non_blocking.csv      86 条非阻塞型 bug 标注
    bugs_master.csv                 171 行主表（P1/P4 的唯一入口）
    artifact_manifest.csv           169 个补丁清单（补丁 ↔ bug 的关联）
    p0_artifact_checks.md           一致性校验报告

xlsx 的三个坑（本脚本已处理）:
  1. 两张表末尾有一整块「按项目汇总 + sum:」的统计区，不是数据行；
  2. boltdb#392 / boltdb#240 两行的 BugID 被填进了 commit hash 列（这两个 bug 没有修复 commit）；
  3. 表头有重名列（两处 Misc），需要自动加后缀。

不依赖 openpyxl：xlsx 本质是 zip + XML，用标准库直接解析。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKGRELNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

BUGID_RE = re.compile(r"^[A-Za-z][\w.-]*#\d+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

APP_ALIAS = {
    "docker": "docker", "moby": "docker",
    "kubernetes": "kubernetes",
    "etcd": "etcd",
    "cockroachdb": "cockroachdb", "cockroach": "cockroachdb",
    "grpc": "grpc-go", "grpc-go": "grpc-go",
    "boltdb": "boltdb", "bolt": "boltdb",
}


def pkg_name(v: str) -> str:
    v = (v or "").strip().lower()
    return APP_ALIAS.get(v, v)


# ---------------- xlsx 解析 ----------------

def read_xlsx(path: Path) -> dict[str, list[dict[str, str]]]:
    """返回 {工作表名: [ {列字母: 值}, ... ]}，第 1 行为表头。"""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(NS + "t")) for si in root.findall(NS + "si")]

    rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in z.namelist():
        for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall(PKGRELNS + "Relationship"):
            target = rel.get("Target", "")
            if not target.startswith("/"):
                target = "xl/" + target.lstrip("./")
            rels[rel.get("Id", "")] = target

    out: dict[str, list[dict[str, str]]] = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(NS + "sheet"):
        target = rels.get(sh.get(RELNS + "id") or "")
        if not target or target not in z.namelist():
            continue
        rows: list[dict[str, str]] = []
        for r in ET.fromstring(z.read(target)).iter(NS + "row"):
            cells: dict[str, str] = {}
            for c in r.iter(NS + "c"):
                m = re.match(r"[A-Z]+", c.get("r") or "")
                if not m:
                    continue
                if c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(NS + "t"))
                else:
                    v = c.find(NS + "v")
                    if v is None or v.text is None:
                        continue
                    val = shared[int(v.text)] if c.get("t") == "s" else v.text
                cells[m.group()] = val.strip()
            if cells:
                rows.append(cells)
        out[sh.get("name") or ""] = rows
    return out


def col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def to_dicts(rows: list[dict[str, str]], header_idx: int = 0,
             sub_idx: int | None = None) -> tuple[list[str], list[dict[str, str]]]:
    """表头映射成唯一字段名；去掉全空行。

    部分工作表是多行表头（application 的 A1 是标题 "table 1"，真正的表头在第 2 行，
    第 3 行是子表头 "# deadlock / #non-deadlock"），所以支持指定 header_idx / sub_idx。
    """
    if len(rows) <= header_idx:
        return [], []
    hdr = rows[header_idx]
    sub = rows[sub_idx] if sub_idx is not None and len(rows) > sub_idx else {}
    all_cols = {c for r in rows for c in r}
    fields: list[str] = []
    mapping: dict[str, str] = {}
    for c in sorted(all_cols, key=col_index):
        base = (hdr.get(c) or sub.get(c) or f"col{c}").strip()
        name, k = base, 2
        while name in fields:
            name = f"{base}_{k}"
            k += 1
        fields.append(name)
        mapping[c] = name
    start = (sub_idx if sub_idx is not None else header_idx) + 1
    out = []
    for r in rows[start:]:
        d = {mapping[c]: v for c, v in r.items() if c in mapping}
        if any(v for v in d.values()):
            out.append(d)
    return fields, out


def excel_serial_to_date(v: str) -> str:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return v
    if 20000 < n < 60000:
        return (dt.date(1899, 12, 30) + dt.timedelta(days=n)).isoformat()
    return v


# ---------------- 补丁解析 ----------------

def parse_patch(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^commit ([0-9a-f]{40})\s*$", text, re.M)
    sha = m.group(1) if m else path.stem

    lines = text.split("\n")
    subject = ""
    for i, line in enumerate(lines):
        if line.startswith("commit "):
            for nxt in lines[i + 1:]:
                if nxt.startswith("diff --git"):
                    break
                if nxt.startswith("    ") and nxt.strip():
                    subject = nxt.strip()
                    break
            break

    files = re.findall(r"^diff --git a/(.+?) b/", text, re.M)
    ins = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dele = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {
        "subject": subject,
        "changed_files": ";".join(files),
        "n_files": len(files),
        "insertions": ins,
        "deletions": dele,
    }


# ---------------- 主流程 ----------------

def _find_up(name: str, start: Path, levels: int = 3) -> Path:
    """从 start 起向上最多 levels 级查找名为 name 的目录。

    交付目录嵌在仓库里（<repo>/1240012318/repro），artifact 这类共享材料
    可能留在仓库根而不随个人目录移动，所以不能只往上数固定层数。
    """
    p = start
    for _ in range(levels):
        if (p / name).is_dir():
            return p / name
        p = p.parent
    return start / name


def main() -> int:
    here = Path(__file__).resolve()
    team = here.parents[2]
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default=str(_find_up("go-concurrency-bugs-master", team)))
    ap.add_argument("--outdir", default=str(here.parents[1] / "data"))
    args = ap.parse_args()

    art = Path(args.artifact)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if not (art / "bug table.xlsx").exists():
        raise SystemExit(f"[x] 找不到 artifact: {art}")

    sheets = read_xlsx(art / "bug table.xlsx")
    print("[.] 工作表:", list(sheets))

    def dump(name: str, fields: list[str], rows: list[dict]) -> Path:
        fn = outdir / name
        with fn.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return fn

    # ---- 1) application（Table 1）----
    a_fields, a_rows = to_dicts(sheets.get("application", []), header_idx=1, sub_idx=2)
    a_rows = [r for r in a_rows
              if (r.get("app.") or "").strip() and (r.get("Stars") or "").strip().isdigit()]
    date_fields = [f for f in a_fields if f in ("Start", "Date")]
    for r in a_rows:
        for f in date_fields:
            r[f] = excel_serial_to_date(r.get(f, ""))
    dump("bug_table_application.csv", a_fields, a_rows)
    print(f"    application: {len(a_rows)} 个项目")

    # ---- 2) blocking / non-blocking 标注 ----
    tables: dict[str, list[dict]] = {}
    for sheet, behavior in (("blocking", "blocking"), ("non-blocking", "non-blocking")):
        fields, rows = to_dicts(sheets.get(sheet, []))
        clean = []
        for r in rows:
            b = (r.get("commit hash") or "").strip()
            c = (r.get("BugID") or "").strip()
            if c.lower() == "none":
                c = ""
            # 坑 2：BugID 被填进了 commit hash 列（这两个 bug 没有修复 commit）
            if BUGID_RE.match(b) and not BUGID_RE.match(c):
                b, c = "", b
                r["BugID"] = c
                r["commit hash"] = ""
            # 数据行判定：有 40 位 commit hash，或有 BugID（表尾汇总行两者都没有）
            is_sha = bool(SHA_RE.match(b.lower()))
            if not is_sha and not BUGID_RE.match(c):
                continue
            r["_sha"] = b.lower() if is_sha else ""
            r["_behavior"] = behavior
            r["uid"] = c or f"{pkg_name(r.get('application',''))}@{r['_sha'][:8]}"
            clean.append(r)
        tables[behavior] = clean
        dump(f"bug_table_{sheet.replace('-', '_')}.csv", fields + ["_sha", "_behavior", "uid"], clean)
        print(f"    {sheet}: {len(clean)} 条"
              f"（无 commit hash {sum(1 for r in clean if not r['_sha'])}，"
              f"无 BugID {sum(1 for r in clean if not r.get('BugID'))}）")

    # ---- 3) 补丁 ----
    patches = []
    for behavior, sub in (("blocking", "blocking-bugs"), ("non-blocking", "non-blocking-bugs")):
        for p in sorted((art / sub).rglob("*.txt")):
            rec = parse_patch(p)
            rec.update({
                "behavior": behavior,
                "app": p.parent.name,
                "fix_commit": p.stem,
                "patch_file": p.relative_to(art).as_posix(),
            })
            patches.append(rec)
    nb = sum(1 for p in patches if p["behavior"] == "blocking")
    print(f"[.] 补丁: {len(patches)} 个（blocking {nb} / non-blocking {len(patches)-nb}）")

    # ---- 4) 关联：补丁 ↔ bug ----
    bug_by_sha12 = {}
    for r in tables["blocking"] + tables["non-blocking"]:
        if r["_sha"]:
            bug_by_sha12.setdefault(r["_sha"][:12], r)

    manifest = []
    for p in patches:
        t = bug_by_sha12.get(p["fix_commit"].lower()[:12], {})
        manifest.append({
            "bug_id": t.get("BugID", ""),
            "app": p["app"],
            "behavior": p["behavior"],
            "reproduced": t.get("Reproduced?", ""),
            "fix_commit": p["fix_commit"],
            "subject": p["subject"],
            "n_files": p["n_files"],
            "insertions": p["insertions"],
            "deletions": p["deletions"],
            "patch_size": t.get("patch size") or t.get("patch-size") or "",
            "matched": "1" if t else "0",
            "patch_file": p["patch_file"],
        })
    dump("artifact_manifest.csv", list(manifest[0].keys()), manifest)
    unmatched = [m["fix_commit"] for m in manifest if m["matched"] == "0"]
    print(f"[ok] artifact_manifest.csv: {len(manifest)} 行（未匹配 {len(unmatched)}）")

    # ---- 5) 171 行主表 ----
    patch_by_sha32 = {p["fix_commit"].lower(): p for p in patches}
    master = []
    for r in tables["blocking"] + tables["non-blocking"]:
        sha = r["_sha"].lower()
        p = patch_by_sha32.get(sha)
        master.append({
            "uid": r.get("uid", ""),
            "bug_id": r.get("BugID", ""),
            "app": pkg_name(r.get("application", "")),
            "behavior": r["_behavior"],
            "reproduced": r.get("Reproduced?", ""),
            "fix_commit": sha,
            "has_patch": "1" if p else "0",
            "patch_file": p["patch_file"] if p else "",
            "patch_size": r.get("patch size") or r.get("patch-size") or "",
            "cause_group": ("message_passing" if (r.get("message") or "").strip() == "1"
                            else "shared_memory" if (r.get("shared") or "").strip() == "1" else ""),
            "fix_strategy": "",
            "notes": "",
        })
    dump("bugs_master.csv", list(master[0].keys()), master)
    print(f"[ok] bugs_master.csv: {len(master)} 行（有补丁 {sum(1 for m in master if m['has_patch']=='1')}）")

    # ---- 5b) P4 的复现目标：作者标记 Reproduced?=1 的 bug ----
    targets = [m for m in master if m["reproduced"] == "1"]
    dump("repro_targets.csv",
         ["uid", "bug_id", "app", "behavior", "fix_commit", "has_patch", "patch_file", "cause_group"],
         targets)
    nb_t = sum(1 for m in targets if m["behavior"] == "blocking")
    print(f"[ok] repro_targets.csv: {len(targets)} 条（blocking {nb_t} / non-blocking {len(targets)-nb_t}）")

    # ---- 6) 校验报告 ----
    def counts(rows, col):
        return Counter((r.get(col) or "").strip() for r in rows)

    lines = ["# P0 artifact 一致性校验", "",
             f"- artifact：`{art}`",
             f"- 生成时间：{dt.datetime.now():%Y-%m-%d %H:%M}", "",
             "## 数量对账", "", "| 项 | 本仓库解析 | 论文 | 差异 |", "|---|---|---|---|"]
    bl, nbl = tables["blocking"], tables["non-blocking"]
    lines.append(f"| blocking bug 行 | {len(bl)} | 85 | {len(bl)-85:+d} |")
    lines.append(f"| non-blocking bug 行 | {len(nbl)} | 86 | {len(nbl)-86:+d} |")
    lines.append(f"| 合计 | {len(bl)+len(nbl)} | 171 | {len(bl)+len(nbl)-171:+d} |")
    lines.append(f"| 补丁文件 | {len(patches)} | — | — |")
    lines.append(f"| 无补丁的 bug | {sum(1 for m in master if m['has_patch']=='0')} | — | — |")
    lines.append(f"| 唯一 uid | {len({m['uid'] for m in master})} | 171 | {len({m['uid'] for m in master})-171:+d} |")
    lines.append(f"| 有 BugID 的行 | {sum(1 for m in master if m['bug_id'])} | — | — |")
    lines.append("")

    lines += ["## Reproduced? 分布（P4 的 ground truth）", "",
              "| 分组 | 标 1 | 标 0 | 空白 | 论文 |", "|---|---|---|---|---|"]
    for name, rows, paper in (("blocking", bl, 21), ("non-blocking", nbl, 20)):
        c = counts(rows, "Reproduced?")
        lines.append(f"| {name} | {c.get('1',0)} | {c.get('0',0)} | {c.get('',0)} | {paper} |")
    lines.append("")

    lines += ["## 致因维度自校验（论文核心结论）", "",
              "口径：一行同时标了 shared 和 message 时按 message 计（论文即如此，共 1 行：kubernetes#11298）。",
              "", "| 分组 | shared_memory | message_passing | 合计 | 论文 |", "|---|---|---|---|---|"]
    for name, rows in (("blocking", bl), ("non-blocking", nbl)):
        ms = sum(1 for r in rows if (r.get("message") or "").strip() == "1")
        sh = sum(1 for r in rows if (r.get("message") or "").strip() != "1"
                and (r.get("shared") or "").strip() == "1")
        both = sum(1 for r in rows if (r.get("message") or "").strip() == "1"
                   and (r.get("shared") or "").strip() == "1")
        paper = "36 / 49" if name == "blocking" else "69 / 17"
        lines.append(f"| {name} | {sh} | {ms} | {sh+ms} | {paper} |")
        if both:
            pct = 100.0 * ms / (sh + ms)
            lines.append(f"| （其中混合型 {both} 行，message 占比 {pct:.1f}%） | | | | |")
    lines.append("")

    lines += ["## 与论文的口径差异（需在报告中披露）", ""]
    nopatch = [m for m in master if m["has_patch"] == "0"]
    lines.append(
        f"1. **补丁 169 个 vs bug 171 个**：{len(nopatch)} 个 BoltDB blocking bug 在表里没有 commit hash"
        "（作者把 BugID 直接填进了 commit hash 列），所以没有独立补丁。"
        "这两个恰好就是论文中内置 deadlock detector 唯二能检出的 bug。"
    )
    dup_uid = Counter(m["uid"] for m in master)
    dups = {k: v for k, v in dup_uid.items() if v > 1}
    lines.append(
        f"2. **171 行对应 {len(dup_uid)} 个唯一 uid**：{sum(dups.values())-len(dups)} 行是同一 bug 的多处修复"
        f"（{', '.join(f'{k}×{v}' for k, v in dups.items())}），统计'bug 数'时需按 uid 去重。"
    )
    nb_hit = sum(1 for m in master if m["behavior"] == "non-blocking" and m["reproduced"] == "1")
    lines.append(
        f"3. **Reproduced?=1 共 {sum(1 for m in master if m['reproduced']=='1')} 条**（blocking 21 + non-blocking {nb_hit}），"
        "论文说的 41 = 21 + 20，non-blocking 多出 3 条；推测论文的 20 是'进入 detector 评测'的子集，"
        "P4 以 `repro_targets.csv` 为准，P5 再按论文口径筛。"
    )
    lines.append("")


    if nopatch:
        lines += [f"## 无独立补丁的 bug（{len(nopatch)} 条）", "",
                  "| BugID | app | behavior | Reproduced |", "|---|---|---|---|"]
        for m in nopatch:
            lines.append(f"| {m['bug_id']} | {m['app']} | {m['behavior']} | {m['reproduced'] or '(空)'} |")
        lines.append("")

    if unmatched:
        lines += [f"## 未匹配到标注行的补丁（{len(unmatched)} 个）", ""]
        lines += [f"- `{s}`" for s in unmatched]
        lines.append("")

    (outdir / "p0_artifact_checks.md").write_text("\n".join(lines), encoding="utf-8")
    print("[ok] p0_artifact_checks.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
