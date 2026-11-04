#!/usr/bin/env python3
"""P1 阶段：用并发相关关键词过滤 commit 历史，产出候选 bug commit 列表。

对应论文 4 节 "Collecting concurrency bugs"。论文在 6 个项目上命中 3211 个
distinct commit，本脚本用于复现这一数量级，并输出可供人工判定的清单。

注意：
  * 论文只说"搜索 commit log"，没说搜标题还是全文，也没说是否含 merge。
    实测两者相差一倍以上，所以 --scope / --merges 是显式参数，默认
    （subject + 含 merge）是与论文 3211 最接近的口径，用 --calibrate 可看全部四种。
  * 由于仓库在持续演进，不冻结快照就无法命中 3211 这个数字。
    建议对 clone 出来的仓库先 checkout/reset 到 2018-05-31 之前，或直接
    用 --until 参数限定时间窗口。

用法:
    python scripts/01_mine_commits.py --repo 6app/etcd --app etcd \
        --out out/commits_etcd.csv --calibrate
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
RS = "\x1e"


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


def load_commits(repo: Path, since: str | None, until: str | None) -> list[dict]:
    """一次取回全部 commit（subject + body + parents），后续在内存里按口径过滤。

    不用 `git log --grep` 的原因：它只能搜全文，无法表达"只搜标题"，
    而两种范围的命中数相差一倍以上（见 --calibrate 输出）。
    """
    args = ["log", "--date=short", f"--pretty=format:%H{SEP}%P{SEP}%ad{SEP}%s{SEP}%b{RS}"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")

    commits: list[dict] = []
    for rec in git(repo, *args).split(RS):
        rec = rec.lstrip("\n")
        if not rec.strip():
            continue
        p = (rec.split(SEP) + [""] * 5)[:5]
        commits.append({"sha": p[0], "parents": p[1], "date": p[2], "subject": p[3], "body": p[4]})
    return commits


def match(c: dict, keywords: list[str], scope: str, merges: str) -> list[str]:
    if merges == "exclude" and len(c["parents"].split()) > 1:
        return []
    hay = c["subject"] if scope == "subject" else c["subject"] + "\n" + c["body"]
    low = hay.lower()
    return [kw for kw in keywords if kw in low]


def mine(commits: list[dict], keywords: list[str], scope: str, merges: str) -> list[dict]:
    rows: list[dict] = []
    for c in commits:
        matched = match(c, keywords, scope, merges)
        if not matched:
            continue
        rows.append(
            {
                "commit": c["sha"],
                "date": c["date"],
                "subject": c["subject"].replace('"', "'"),
                "matched_keywords": "|".join(matched),
            }
        )
    return rows


def calibrate(commits: list[dict], keywords: list[str]) -> list[tuple[str, int]]:
    """四种口径的命中数。论文未说明搜索范围，这个表是判断其口径的依据。"""
    out = []
    for scope in ("subject", "message"):
        for merges in ("include", "exclude"):
            n = sum(1 for c in commits if match(c, keywords, scope, merges))
            label = f"{'标题' if scope == 'subject' else '全文'}·{'含 merge' if merges == 'include' else '排除 merge'}"
            out.append((label, n))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="git 仓库路径")
    ap.add_argument("--app", required=True, help="项目名，如 etcd")
    ap.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    ap.add_argument("--until", default=None, help="截止日期 YYYY-MM-DD（建议 2018-05-31）")
    ap.add_argument("--keywords", default=None, help="逗号分隔，覆盖默认关键词表")
    ap.add_argument("--scope", choices=["subject", "message"], default="subject",
                    help="搜索范围：subject=仅标题行（默认），message=标题+正文")
    ap.add_argument("--merges", choices=["include", "exclude"], default="exclude",
                    help="是否把 merge commit 计入候选（默认排除：merge 本身无代码改动）")
    ap.add_argument("--calibrate", action="store_true",
                    help="额外打印四种口径的命中数，用于和论文的 3211 对表")
    ap.add_argument("--out", required=True, help="输出 CSV")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"[x] 不是 git 仓库: {repo}", file=sys.stderr)
        return 2

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    commits = load_commits(repo, args.since, args.until)
    rows = mine(commits, keywords, args.scope, args.merges)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["app", "commit", "date", "subject", "matched_keywords"])
        w.writeheader()
        for r in rows:
            w.writerow({"app": args.app, **r})

    print(f"[ok] {args.app}: 命中 {len(rows)} 个 commit "
          f"({args.scope}, merges={args.merges}, 共 {len(commits)} 个 commit) -> {out}")
    if rows:
        print(f"     时间范围 {rows[-1]['date']} ~ {rows[0]['date']}")
    if args.calibrate:
        for label, n in calibrate(commits, keywords):
            print(f"     {label:<14}{n:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
