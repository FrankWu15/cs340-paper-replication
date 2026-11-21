#!/usr/bin/env python3
"""06_evolution.py — 论文 Figure 2 / Figure 3：并发原语使用比例随时间的变化。

论文口径（§3.2 末段）：
    Figures 2 and 3 present the shared-memory and message-passing primitive
    usages in the six applications from Feb 2015 to May 2018.
    「usage proportion」= 该类原语 / 全部原语。

测量方法：
    1. 按季度取采样点（2015-02-01 … 2018-05-01，正好是论文横轴 14 个刻度）；
    2. 每个采样点取该日期之前最后一次提交（git rev-list -1 --before=）；
    3. 在 worktree 里 checkout 到该提交，用 tools/goast 解析 Go AST 计数；
    4. 共享内存 = lock_calls + atomic + once + waitgroup + cond
       消息传递 = chan(send+recv) + sync.Pool(Misc)
       口径与 02_static_metrics.py 完全一致（同一份 goast、同样的排除规则）。

    vendor/、third_party/、*_test.go 一律不计入分子——这是 P2 阶段由论文
    Table 2/4 数字反推出来的口径，改了就与 Table 4 对不上。

用法：
    python 06_evolution.py --out ../../data/evolution_primitive_usage.csv \
        --repo boltdb=../../../6app/boltdb --repo etcd=... --repo grpc-go=...

只依赖 git 与 goast 二进制，不联网（blobless 克隆除外：checkout 时由 git 自己补 blob）。
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# 论文横轴刻度，季度
TICKS = [
    "2015-02-01", "2015-05-01", "2015-08-01", "2015-11-01",
    "2016-02-01", "2016-05-01", "2016-08-01", "2016-11-01",
    "2017-02-01", "2017-05-01", "2017-08-01", "2017-11-01",
    "2018-02-01", "2018-05-01",
]


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
    return proc.stdout.strip()


def commit_before(repo: Path, iso: str) -> str:
    """该日期（含）之前最后一次提交；没有则返回空串。"""
    out = subprocess.run(["git", "-C", str(repo), "rev-list", "-1",
                          f"--before={iso} 23:59:59", "HEAD"],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


BAD_PATHS = [":(exclude)*/prereqs/testdata/*"]


def wipe(wt: Path) -> None:
    """清空 worktree 里的文件，保留 .git 指针文件。"""
    for p in wt.iterdir():
        if p.name == ".git":
            continue
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except OSError:
                pass


INVALID_CHARS = set('*?<>|"\\:')


def safe_name(path: str) -> bool:
    if any(ch in INVALID_CHARS for ch in path):
        return False
    return not any(seg in ("vendor", "Godeps", "third_party", "testdata")
                   for seg in path.split("/"))


def materialize(repo: Path, sha: str, dest: Path) -> tuple[int, int]:
    """不 checkout，直接把需要的 .go 文件从对象库取出来写到 dest。

    用于 Windows 无法建出的路径（cockroachdb 的 prereqs/testdata 里有 `a[]*?~ $%#.go`）。
    只取非测试、非 vendor 的 .go，正好是计数需要的全部输入。

    注意 `git cat-file --batch` 吃的是**对象名**不是路径，所以先 ls-tree 拿 blob sha。
    """
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", sha],
                             capture_output=True, text=True)
    entries: list[tuple[str, str]] = []
    for line in listing.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob":
            continue
        if not path.endswith(".go") or path.endswith("_test.go"):
            continue
        if not safe_name(path):
            continue
        entries.append((parts[2], path))
    if not entries:
        return 0, 0
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
                          input="".join(e[0] + "\n" for e in entries),
                          capture_output=True, text=True)
    data = proc.stdout
    pos = 0
    written = missing = 0
    for _, path in entries:
        nl = data.find("\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].split()
        if len(header) != 3:          # "<sha> missing" —— 部分克隆没拉到 blob
            missing += 1
            pos = nl + 1
            continue
        size = int(header[2])
        body = data[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1
        out = dest / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8", errors="ignore")
        written += 1
    return written, missing


def switch_to(wt: Path, sha: str) -> None:
    """切到指定提交；遇到 Windows 非法文件名（cockroachdb 的 testdata）时降级。"""
    proc = subprocess.run(["git", "-C", str(wt), "checkout", "-q", "--detach", sha],
                          capture_output=True, text=True)
    if proc.returncode == 0:
        return
    err = (proc.stderr or "").strip().splitlines()
    msg = err[0] if err else "unknown"
    print(f"[!!] checkout {sha[:8]} 失败: {msg} -> 改用 pathspec 排除法", flush=True)
    wipe(wt)
    r = subprocess.run(["git", "-C", str(wt), "checkout", sha, "--", ".", *BAD_PATHS],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"降级 checkout 仍失败: {r.stderr.strip()[:300]}")


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["app", "tick", "commit", "commit_date", "go_files", "go_lines",
              "go_sites", "sm", "mp", "total", "sm_pct", "mp_pct", "parse_errors"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def run_goast(goast: str, root: Path, skips: list[str]) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    cmd = [goast, "-root", str(root), "-json", str(tmp)]
    for s in skips:
        cmd += ["-skip", s]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"goast 失败: {proc.stderr.strip()[:400]}")
    data = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)
    return data


def split(app: str, repo: Path, goast: str, ticks: list[str], workroot: Path,
          skips: list[str], catfile: bool = False) -> list[dict]:
    rows: list[dict] = []
    wt = workroot / f"wt-{app}"
    if wt.exists():
        if not catfile:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                           capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
    if catfile:
        wt.mkdir(parents=True, exist_ok=True)

    first = True
    for tick in ticks:
        sha = commit_before(repo, tick)
        if not sha:
            print(f"[..] {app} {tick}: 无提交，跳过", flush=True)
            continue
        # 同一提交在相邻采样点可能重复（仓库不活跃），去重但仍记录
        if catfile:
            wipe(wt)
            n, missing = materialize(repo, sha, wt)
            if n == 0:
                print(f"[..] {app} {tick}: 无 .go 文件，跳过", flush=True)
                continue
            if missing:
                # 少文件会让比例失真（分母变小），宁可整点跳过也不出假数
                print(f"[!!] {app} {tick}: {missing}/{n + missing} 个 blob 拉不下来，跳过该点",
                      flush=True)
                continue
        elif first:
            git(repo, "worktree", "add", "--detach", str(wt), sha)
            first = False
        else:
            switch_to(wt, sha)
        c = run_goast(goast, wt, skips)
        sm = (c["lock_calls"] + c["atomic"] + c["once"]
              + c["waitgroup"] + c["cond"])
        chan = c["chan_send"] + c["chan_recv"]
        mp = chan + c.get("misc_pool", 0)
        total = sm + mp
        rows.append({
            "app": app,
            "tick": tick,
            "commit": sha[:10],
            "commit_date": git(repo, "log", "-1", "--format=%ad", "--date=short", sha),
            "go_files": c["files"],
            "go_lines": c["lines"],
            "go_sites": c["go_stmt_normal"] + c["go_stmt_anonymous"],
            "sm": sm,
            "mp": mp,
            "total": total,
            "sm_pct": round(100.0 * sm / total, 2) if total else 0.0,
            "mp_pct": round(100.0 * mp / total, 2) if total else 0.0,
            "parse_errors": c["parse_errors"],
        })
        print(f"[ok] {app:11s} {tick} {sha[:8]} files={c['files']:5d} "
              f"sm={sm:5d} mp={mp:4d} sm%={rows[-1]['sm_pct']:5.1f}", flush=True)

    if not catfile:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                       capture_output=True)
    shutil.rmtree(wt, ignore_errors=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True,
                    help="app=path，可重复")
    ap.add_argument("--out", required=True)
    ap.add_argument("--goast", default="/tmp/goast")
    ap.add_argument("--workdir", default=tempfile.gettempdir() + "/evolution_wt")
    ap.add_argument("--from-tick", default=TICKS[0])
    ap.add_argument("--to-tick", default=TICKS[-1])
    ap.add_argument("--append", action="store_true", help="追加到已有 CSV")
    ap.add_argument("--catfile", action="store_true",
                    help="不用 checkout，直接从对象库取 .go 文件（Windows 非法路径的兜底）")
    ap.add_argument("--skip", action="append", default=[],
                    help="额外跳过的目录名；默认已含 Godeps（2015-2016 的 vendor 前身）")
    args = ap.parse_args()

    ticks = [t for t in TICKS if args.from_tick <= t <= args.to_tick]
    workroot = Path(args.workdir)
    workroot.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    if args.append and Path(args.out).exists():
        with open(args.out, encoding="utf-8-sig") as f:
            all_rows = list(csv.DictReader(f))
        all_rows = [{k: (int(v) if k in ("sm", "mp", "total", "go_files", "go_lines",
                                        "go_sites", "parse_errors") and str(v).isdigit() else v)
                     for k, v in r.items()} for r in all_rows]

    for spec in args.repo:
        app, _, path = spec.partition("=")
        repo = Path(path).expanduser().resolve()
        if not repo.is_dir():
            print(f"[x] {app}: 目录不存在 {repo}", file=sys.stderr)
            return 2
        rows = split(app, repo, args.goast, ticks, workroot, ["Godeps"] + args.skip,
                     catfile=args.catfile)
        all_rows = [r for r in all_rows if r["app"] != app] + rows
        all_rows.sort(key=lambda r: (r["app"], r["tick"]))
        write_csv(Path(args.out), all_rows)   # 每个应用测完就落盘，后面炸了也不丢
        print(f"[save] {app} -> {args.out}（累计 {len(all_rows)} 行）", flush=True)

    all_rows.sort(key=lambda r: (r["app"], r["tick"]))
    write_csv(Path(args.out), all_rows)
    print(f"[done] {len(all_rows)} 行 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
