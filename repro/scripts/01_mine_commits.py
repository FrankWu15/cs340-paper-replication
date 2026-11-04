#!/usr/bin/env python3
"""P1 阶段：用并发相关关键词过滤 commit 历史，产出候选 bug commit 列表。

对应论文 4 节 "Collecting concurrency bugs"。论文在 6 个项目上命中 3211 个
distinct commit，本脚本用于复现这一数量级，并输出可供人工判定的清单。

注意：
  * git log --grep 默认匹配 commit message 的 subject + body（OR 关系），
    与论文"搜索 commit logs"的做法一致。
  * 由于仓库在持续演进，不冻结快照就无法命中 3211 这个数字。
    建议对 clone 出来的仓库先 checkout/reset 到 2018-05-31 之前，或直接
    用 --until 参数限定时间窗口。

用法:
    python scripts/01_mine_commits.py --repo vendor/etcd --app etcd \
        --until 2018-05-31 --out out/commits_etcd.csv
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

DEFAULT_KEYWORDS = [
    "race",
    "deadlock",
    "synchronization",
    "concurrency",
    "lock",
    "mutex",
    "atomic",
    "compete",
    "context",       # Go 特有：context 库
    "once",          # Go 特有：sync.Once
    "goroutine leak",  # Go 特有：goroutine 泄漏
]

SEP = "\x1f"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
    return proc.stdout


def mine(repo: Path, keywords: list[str], since: str | None, until: str | None) -> list[dict]:
    args = ["log", "--no-merges", "-i", "--date=short", f"--pretty=format:%H{SEP}%ad{SEP}%s"]
    for kw in keywords:
        args += ["--grep", kw]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")

    rows: list[dict] = []
    seen: set[str] = set()
    for line in git(repo, *args).splitlines():
        parts = line.split(SEP)
        if len(parts) < 3:
            continue
        sha, date, subject = parts[0], parts[1], SEP.join(parts[2:])
        if sha in seen:
            continue
        seen.add(sha)
        low = subject.lower()
        matched = [kw for kw in keywords if kw in low]
        rows.append(
            {
                "commit": sha,
                "date": date,
                "subject": subject.replace('"', "'"),
                # 仅基于 subject 的近似命中，body 中的命中看不到，属已知偏差
                "matched_keywords": "|".join(matched) if matched else "(body only)",
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="git 仓库路径")
    ap.add_argument("--app", required=True, help="项目名，如 etcd")
    ap.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="截止日期 YYYY-MM-DD（建议 2018-05-31）")
    ap.add_argument("--keywords", default=None, help="逗号分隔，覆盖默认关键词表")
    ap.add_argument("--out", required=True, help="输出 CSV")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"[x] 不是 git 仓库: {repo}", file=sys.stderr)
        return 2

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    rows = mine(repo, keywords, args.since, args.until)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["app", "commit", "date", "subject", "matched_keywords"])
        w.writeheader()
        for r in rows:
            w.writerow({"app": args.app, **r})

    print(f"[ok] {args.app}: 命中 {len(rows)} 个 commit -> {out}")
    if rows:
        print(f"     时间范围 {rows[-1]['date']} ~ {rows[0]['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
