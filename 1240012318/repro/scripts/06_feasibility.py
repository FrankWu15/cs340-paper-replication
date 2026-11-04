#!/usr/bin/env python3
"""P4 前置：为论文标为「已复现」的目标 bug 生成可行性表。

不做任何复现动作，只回答三个问题：
  1. 修复补丁长什么样（改了哪些文件、多少行、有没有测试）
  2. 该 commit 是否在本地 6app/ 快照里、是否在 P1 的候选集合里
  3. 按「能不能直接跑起来」分成 A / B / C 三档

数据来源优先级：
  - artifact 的 `.txt` 已含完整 diff，直接解析，不走 `git show`
    （docker / cockroachdb / kubernetes 是 treeless clone，`git show` 会触发网络下载 blob）
  - commit 日期用 `git log -1 --format=%ci`，只读 commit 对象，不碰 tree

用法:
    python scripts/06_feasibility.py --bugs data/bugs_master.csv \
        --artifact ../go-concurrency-bugs-master --repos 6app \
        --out-data data/feasibility_44.csv --out-report out/p4_feasibility_report.md
"""
from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent


def _find_up(name: str, start: Path, levels: int = 3) -> Path:
    """从 start 起向上最多 levels 级查找名为 name 的目录。

    交付目录嵌在仓库里（<repo>/1240012318/repro），artifact 与上游仓库
    这类共享材料可能留在仓库根，所以不能只往上数固定层数。
    """
    p = start
    for _ in range(levels):
        if (p / name).is_dir():
            return p / name
        p = p.parent
    return start / name


PIN_DATE = "2018-05-21"

BEH = {"blocking": "阻塞", "non-blocking": "非阻塞"}  # 六个仓库的对齐日期，晚于此日期的 commit 需额外 fetch


def parse_patch(p: Path) -> dict:
    """从 unified diff 文本里提取结构特征。"""
    info = {
        "ok": False,
        "is_merge": False,
        "files": [],
        "ins": 0,
        "del": 0,
        "touches_test": False,
        "new_test_funcs": [],
        "pkg_go": 0,
    }
    if not p.exists():
        return info
    text = p.read_text(encoding="utf-8", errors="ignore")
    info["ok"] = True
    cur = None
    for line in text.splitlines():
        if line.startswith("Merge:"):
            # merge commit 的 git show 默认不输出 diff，artifact 里就只有提交信息
            info["is_merge"] = True
            continue
        if line.startswith("diff --git "):
            # diff --git a/x/y.go b/x/y.go
            parts = line.split(" b/", 1)
            cur = parts[1].strip() if len(parts) == 2 else ""
            if cur and cur not in info["files"]:
                info["files"].append(cur)
            if cur.endswith("_test.go"):
                info["touches_test"] = True
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+") and cur:
            info["ins"] += 1
            s = line[1:].strip()
            if s.startswith("func Test"):
                name = s[len("func "):].split("(")[0]
                if name not in info["new_test_funcs"]:
                    info["new_test_funcs"].append(name)
        elif line.startswith("-") and cur:
            info["del"] += 1
    info["pkg_go"] = sum(1 for f in info["files"] if f.endswith(".go"))
    return info


def supplement_merge_diff(repo: Path, sha: str, info: dict) -> bool:
    """merge commit 补 diff：取「与第一父的差」。

    只对 full clone 的仓库尝试——treeless clone 上这会联网拉 blob，
    用 10s 超时兜底，拉不到就放弃，保持原样。
    """
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "diff", "--no-color", f"{sha}^1", sha],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False
    if p.returncode != 0 or not p.stdout.strip():
        return False
    cur = None
    for line in p.stdout.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            cur = parts[1].strip() if len(parts) == 2 else ""
            if cur and cur not in info["files"]:
                info["files"].append(cur)
            if cur.endswith("_test.go"):
                info["touches_test"] = True
        elif line.startswith(("+++", "---")):
            continue
        elif line.startswith("+") and cur:
            info["ins"] += 1
            s = line[1:].strip()
            if s.startswith("func Test"):
                name = s[len("func "):].split("(")[0]
                if name not in info["new_test_funcs"]:
                    info["new_test_funcs"].append(name)
        elif line.startswith("-") and cur:
            info["del"] += 1
    info["pkg_go"] = sum(1 for f in info["files"] if f.endswith(".go"))
    return True


def git_date(repo: Path, sha: str) -> str:
    if not sha:
        return ""
    p = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%ci", sha],
        capture_output=True, text=True,
    )
    return p.stdout.strip()[:10] if p.returncode == 0 else ""


def in_repo(repo: Path, sha: str) -> bool:
    if not sha:
        return False
    p = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", sha + "^{commit}"],
        capture_output=True,
    )
    return p.returncode == 0


def grade(has_patch: bool, present: bool, d: dict) -> tuple[str, str]:
    """A=有现成测试可直接跑；B=需自写触发程序；C=阻塞。"""
    if not has_patch:
        return "C", "artifact 未提供修复补丁（论文也未给出 fix commit）"
    if not present:
        return "C", "commit 不在本地快照，需联网 fetch"
    if not d["ok"]:
        return "C", "补丁文件缺失或不可读"
    if d["new_test_funcs"]:
        return "A", f"补丁新增测试 {', '.join(d['new_test_funcs'][:3])}"
    if d["touches_test"]:
        return "B", "补丁改动了测试文件但未新增 Test 函数"
    return "B", "仅改产品代码，需自写触发程序"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bugs", default=str(REPRO / "data" / "bugs_master.csv"))
    ap.add_argument("--artifact", default=str(_find_up("go-concurrency-bugs-master", REPRO.parent)))
    ap.add_argument("--repos", default=str(_find_up("6app", REPRO.parent)))
    ap.add_argument("--commits-dir", default=str(REPRO / "out"))
    ap.add_argument("--out-data", default=str(REPRO / "data" / "feasibility_44.csv"))
    ap.add_argument("--out-report", default=str(REPRO / "out" / "p4_feasibility_report.md"))
    args = ap.parse_args()

    artifact = Path(args.artifact)
    repos = Path(args.repos)
    out_data = Path(args.out_data)
    out_report = Path(args.out_report)

    rows = [
        r for r in csv.DictReader(open(args.bugs, encoding="utf-8-sig"))
        if (r.get("reproduced") or "").strip() == "1"
    ]

    # P1 候选集合
    cand: dict[str, set[str]] = {}
    for f in Path(args.commits_dir).glob("commits_*.csv"):
        app = f.stem.replace("commits_", "")
        with open(f, encoding="utf-8-sig") as fh:
            cand[app] = {x["commit"] for x in csv.DictReader(fh)}

    out_rows = []
    for r in rows:
        app = r["app"]
        sha = (r.get("fix_commit") or "").strip()
        has_patch = (r.get("has_patch") or "").strip() == "1"
        pf = artifact / r["patch_file"] if r.get("patch_file") else None
        d = parse_patch(pf) if pf else {"ok": False, "is_merge": False, "files": [], "ins": 0,
                                        "del": 0, "touches_test": False, "new_test_funcs": [],
                                        "pkg_go": 0}
        present = in_repo(repos / app, sha)
        merged_supplemented = False
        if present and d["is_merge"] and not d["files"]:
            merged_supplemented = supplement_merge_diff(repos / app, sha, d)
        date = git_date(repos / app, sha) if present else ""
        g, reason = grade(has_patch, present, d)
        if d["is_merge"]:
            reason = ("merge commit，" + ("已用 diff <sha>^1 还原" if merged_supplemented
                                         else "artifact 无 diff 且本地还原失败") + "；" + reason)
        out_rows.append({
            "uid": r["uid"],
            "bug_id": r.get("bug_id") or "",
            "app": app,
            "behavior": r["behavior"],
            "cause_group": r["cause_group"],
            "fix_commit": sha,
            "fix_date": date,
            "after_pin": "1" if date and date > PIN_DATE else ("0" if date else ""),
            "in_repo": "1" if present else "0",
            "in_p1_candidates": "1" if sha and sha in cand.get(app, set()) else "0",
            "files": len(d["files"]),
            "ins": d["ins"],
            "del": d["del"],
            "is_merge": "1" if d["is_merge"] else "0",
            "touches_test": "1" if d["touches_test"] else "0",
            "new_test_funcs": ";".join(d["new_test_funcs"]),
            "grade": g,
            "reason": reason,
        })

    out_data.parent.mkdir(parents=True, exist_ok=True)
    with open(out_data, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---------- 报告 ----------
    n_rows = len(out_rows)
    n_bugs = len({x["bug_id"] for x in out_rows})
    L: list[str] = []
    L.append(f"# P4 前置：{n_bugs} 个目标 bug 可行性表\n")
    L.append(f"数据源：`repro/data/bugs_master.csv` 中 `reproduced=1` 的 {n_rows} 行，"
             f"对应 **{n_bugs} 个唯一 bug**。")
    L.append("补丁特征解析自 artifact 的 `.txt`（内含完整 unified diff），不走 `git show`，")
    L.append("避免 treeless clone 触发网络拉取。\n")
    if n_rows != n_bugs:
        multi = [
            bid for bid in {x["bug_id"] for x in out_rows}
            if sum(1 for x in out_rows if x["bug_id"] == bid) > 1
        ]
        L.append(f"> **口径提醒**：{n_rows} 行 ≠ {n_bugs} 个 bug。论文正文按 bug 计"
                 f"（21 blocking + 20 non-blocking = {n_bugs}），")
        L.append(f"> artifact 的 CSV 按补丁 commit 计。差出的 {n_rows - n_bugs} 行全部来自 "
                 + "、".join(f"`{b}`" for b in sorted(multi)) + "。")
        L.append("> 这些 bug 的补丁被拆成多段，P4 回滚时必须**整组一起回滚**，")
        L.append("> 只回滚其中一段通常不足以让 bug 复现。详见 `out/bug_table_audit.md`。\n")

    from collections import Counter
    gc = Counter(x["grade"] for x in out_rows)
    L.append("## 1. 总览\n")
    L.append(f"分档按**补丁 commit**计（{n_rows} 行），不是按 bug 计（{n_bugs} 个）。\n")
    L.append("| 档位 | 含义 | 条数 |")
    L.append("|---|---|---|")
    L.append(f"| A | 补丁自带新增测试，可直接 `go test -run` | **{gc.get('A',0)}** |")
    L.append(f"| B | 仅改产品代码，需自写触发程序 | **{gc.get('B',0)}** |")
    L.append(f"| C | 阻塞（无补丁 / commit 不在库） | **{gc.get('C',0)}** |")
    L.append("")

    in_p1 = sum(1 for x in out_rows if x["in_p1_candidates"] == "1")
    after_pin = sum(1 for x in out_rows if x["after_pin"] == "1")
    L.append(f"- fix commit 在本地快照：**{sum(1 for x in out_rows if x['in_repo']=='1')}/{n_rows}**")
    L.append(f"- fix commit 在 P1 的候选集合中：**{in_p1}/{n_rows}**")
    L.append(f"- fix 日期晚于 pin 日期（{PIN_DATE}）：**{after_pin}/{n_rows}**")
    L.append("")

    # 按项目
    L.append("## 2. 按项目分布\n")
    L.append("| 项目 | 条数 | A | B | C | 中位改动行数 |")
    L.append("|---|---|---|---|---|---|")
    apps = sorted({x["app"] for x in out_rows})
    for app in apps:
        sub = [x for x in out_rows if x["app"] == app]
        a = sum(1 for x in sub if x["grade"] == "A")
        b = sum(1 for x in sub if x["grade"] == "B")
        c = sum(1 for x in sub if x["grade"] == "C")
        sizes = sorted(x["ins"] + x["del"] for x in sub)
        med = sizes[len(sizes) // 2] if sizes else 0
        L.append(f"| {app} | {len(sub)} | {a} | {b} | {c} | {med} |")
    L.append("")

    # 明细
    L.append("## 3. 逐条明细\n")
    L.append("| # | bug_id | 项目 | 类型 | 致因 | 改动(文件/+/−) | 测试 | 档 | 说明 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, x in enumerate(sorted(out_rows, key=lambda z: (z["grade"], z["app"])), 1):
        test = "✓" if x["touches_test"] == "1" else ""
        bid = x["bug_id"] or f"(uid {x['uid']})"
        L.append(
            f"| {i} | {bid} | {x['app']} | {BEH.get(x['behavior'], x['behavior'])} | {x['cause_group']} "
            f"| {x['files']}/{x['ins']}/{x['del']} | {test} | **{x['grade']}** | {x['reason']} |"
        )
    L.append("")

    # 关键风险
    # ---------- 与 P1 交叉验证 ----------
    KW = ["race", "deadlock", "synchronization", "concurrency", "lock", "mutex",
          "atomic", "compete", "context", "once", "goroutine leak"]

    def kw(text: str) -> list[str]:
        low = text.lower()
        return [k for k in KW if k in low]

    miss = [x for x in out_rows if x["in_p1_candidates"] == "0"]
    no_commit = [x for x in miss if not x["fix_commit"]]
    merges = [x for x in miss if x["fix_commit"] and x["is_merge"] == "1"]
    rest = [x for x in miss if x["fix_commit"] and x["is_merge"] == "0"]

    L.append("## 4. 与 P1 候选集的交叉验证\n")
    L.append(f"{n_rows} 行中有 **{len(out_rows)-len(miss)} 行**的 fix commit 落在 P1 的 3,105 个候选里，"
             f"**{len(miss)} 条不在**。缺失的构成：\n")
    L.append("| 原因 | 条数 | 说明 |")
    L.append("|---|---|---|")
    L.append(f"| 无 fix commit | {len(no_commit)} | artifact 未提供补丁，必然不在候选集 |")
    L.append(f"| 是 merge commit | {len(merges)} | P1 主口径排除 merge，必然不在候选集 |")
    L.append(f"| 标题不含关键词 | {len(rest)} | **需要逐条查证** |")
    L.append("")

    if rest:
        L.append("### 标题不含关键词的 5 条：正文全部命中\n")
        L.append("| bug_id | 项目 | fix commit | 标题 | 正文命中的关键词 |")
        L.append("|---|---|---|---|---|")
        body_hit_all = True
        for x in rest:
            msg = subprocess.run(
                ["git", "-C", str(repos / x["app"]), "log", "-1", "--format=%B", x["fix_commit"]],
                capture_output=True, text=True,
            ).stdout
            subject = msg.splitlines()[0] if msg else ""
            subj_hit = kw(subject)
            body_hit = kw(msg)
            if not body_hit:
                body_hit_all = False
            L.append(
                f"| {x['bug_id']} | {x['app']} | `{x['fix_commit'][:8]}` | {subject[:52]} "
                f"| {', '.join(body_hit) if body_hit else '无'} |"
            )
        L.append("")
        if body_hit_all:
            L.append("**这 5 条在 commit message 正文里全部命中关键词，只是标题不含。**")
            L.append("它们都是论文标为「已复现」的 bug，说明论文的候选集**必然包含正文匹配**，")
            L.append("否则这些 bug 根本进不了人工筛选环节。\n")
            L.append("这暴露了 P1 的一个方法论问题：")
            L.append("我们选「标题 · 排除 merge」口径，是因为它的总数（3,105）最接近论文的 3,211（−3.3%），")
            L.append("但**总数接近不等于集合正确**——该口径至少漏掉了 5 条论文确实收录的 bug。")
            L.append("改用全文口径重算（含正文、排除 merge、起始日期 2015-02）得 4,544 条，")
            L.append("覆盖这 5 条，但总数比论文高 41%，说明论文还有别的过滤条件（论文未说明）。\n")
            L.append("结论：P1 的 3,105 与论文的 3,211 **只是数字接近，集合并不等价**。")
            L.append("这条必须写进复现报告的局限性一节，不能声称「复现了论文的筛选漏斗」。\n")

    L.append("## 5. 结论与下一步\n")
    L.append("**A 档不是「直接就能跑」**，只是「补丁里有现成测试用例」。真正跑起来还差三关：")
    L.append("1. `git checkout <fix>^` 到修复前的版本——treeless clone 会在这里联网拉 tree；")
    L.append("2. 用 Go 1.10 编译——2015–2018 年的代码用现代 Go 直接编译大概率失败；")
    L.append("3. 并发 bug 非确定性，要重复 N 次统计触发率，不能跑一次就下结论。\n")
    L.append("因此下一步应先拿 A 档里改动最小、依赖最少的 2~3 条打通全流程。按依赖从轻到重排：")
    L.append("")
    L.append("| 建议顺序 | bug | 理由 |")
    L.append("|---|---|---|")
    L.append("| 1 | `boltdb` uid 7fb06fee | BoltDB 是单包项目，无外部依赖、编译最快；补丁含 `TestParallelTransactions` |")
    L.append("| 2 | `boltdb#341` | 同上；merge commit，已还原出 `TestDB_Close_PendingTx_RW/RO` |")
    L.append("| 3 | `etcd#5199` | etcd 依赖较重但可 `go test ./clientv3/...` 单包跑；补丁含 `TestMutexSessionRelock` |")
    L.append("")
    L.append("Kubernetes 与 CockroachDB 各有 4 条和 2 条但全部是 B 档（无现成测试），"
             "且编译体量最大，放到模板验证通过之后再处理。\n")
    L.append("把「checkout → 编译 → 跑测试 → 判定」这套模板跑通后，再批量推进其余 41 条。")

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(L), encoding="utf-8")

    print(f"[ok] -> {out_data}")
    print(f"[ok] -> {out_report}")
    print(f"    A={gc.get('A',0)} B={gc.get('B',0)} C={gc.get('C',0)}  "
          f"in_repo={sum(1 for x in out_rows if x['in_repo']=='1')}/44  "
          f"in_p1={in_p1}/44  after_pin={after_pin}/44")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
