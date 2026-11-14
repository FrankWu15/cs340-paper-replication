#!/usr/bin/env python3
"""校验 6app/ 里的仓库是否都停在 repo.lock.tsv 记录的那个 commit 上。

课程评分要求「记录起始 commit」。仓库源码不入库，别人克隆后必须能确认拿到的是同一份
代码，这个脚本就是那条断言。

退出码 0 = 全部对齐；1 = 有偏差（逐条打印差异）。
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent
PROJECT = REPRO.parent
LOCK = PROJECT / "repo.lock.tsv"


def repo_root() -> Path:
    for cand in ("6app", "repos", "upstream-repos", "src"):
        if (PROJECT / cand).is_dir():
            return PROJECT / cand
    return PROJECT / "6app"


def head_of(repo: Path) -> str | None:
    if not (repo / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main() -> int:
    if not LOCK.exists():
        print(f"[x] 找不到 {LOCK}", file=sys.stderr)
        return 1
    rows = list(csv.DictReader(LOCK.open(encoding="utf-8"), delimiter="\t"))
    root = repo_root()
    print(f"仓库根: {root}\n")
    bad = 0
    for r in rows:
        app, want = r["app"], r["commit"]
        got = head_of(root / app)
        if got is None:
            print(f"[x] {app:<12} 未克隆")
            bad += 1
        elif got != want:
            print(f"[x] {app:<12} HEAD={got[:12]}  期望 {want[:12]}")
            bad += 1
        else:
            print(f"[ok] {app:<12} {got[:12]}")
    print()
    print(f"{len(rows) - bad}/{len(rows)} 对齐" if bad else f"全部 {len(rows)} 个仓库对齐 repo.lock.tsv")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
