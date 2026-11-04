#!/usr/bin/env python3
"""P2 阶段（时间演化）：按月度快照统计并发原语占比，复现论文 Fig 2 / Fig 3。

做法：对每个月末取该时间点的最后一个 commit，用 git worktree 检出到临时目录，
跑 goast，记录 shared-memory / message-passing 占比。用 worktree 是为了不污染
主工作区（主工作区在 P4 还要反复 checkout 到 buggy 版本）。

用法:
    python scripts/03_history_usage.py --repo vendor/etcd --app etcd \
        --start 2015-02 --end 2018-05 --out out/history_etcd.csv
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent
DEFAULT_GOAST = "go run ./tools/goast"  # 建议先 go build -o bin/goast ./tools/goast 再传入


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout.strip()


def month_ends(start: str, end: str) -> list[dt.date]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(dt.date(y, m, calendar.monthrange(y, m)[1]))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def measure(worktree: Path, goast_cmd: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    args = shlex.split(goast_cmd) + ["-root", str(worktree), "-json", str(tmp)]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPRO))
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(proc.stderr.strip())
    data = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)

    sm = data["mutex"] + data["atomic"] + data["once"] + data["waitgroup"] + data["cond"]
    chan = data["chan_make"] + data["chan_send"] + data["chan_recv"]
    mp = chan + data["misc"]
    total = sm + mp
    return {
        "primitives_total": total,
        "shared_memory_pct": round(100.0 * sm / total, 2) if total else 0.0,
        "message_passing_pct": round(100.0 * mp / total, 2) if total else 0.0,
        "goroutine_sites": data["go_stmt_normal"] + data["go_stmt_anonymous"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--start", default="2015-02")
    ap.add_argument("--end", default="2018-05")
    ap.add_argument("--branch", default="HEAD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--goast-cmd", default=DEFAULT_GOAST)
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    rows: list[dict] = []

    for day in month_ends(args.start, args.end):
        stamp = day.isoformat()
        try:
            sha = git(repo, "rev-list", "-1", f"--before={stamp}", args.branch)
        except RuntimeError:
            continue
        if not sha:
            continue

        wt = Path(tempfile.mkdtemp(prefix="hist_"))
        try:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), sha],
                check=True,
                capture_output=True,
                text=True,
            )
            metrics = measure(wt, args.goast_cmd)
        except subprocess.CalledProcessError as exc:
            print(f"[!] {stamp} worktree 失败: {exc.stderr.strip()}", file=sys.stderr)
            continue
        except RuntimeError as exc:
            print(f"[!] {stamp} 统计失败: {exc}", file=sys.stderr)
            continue
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                capture_output=True,
                text=True,
            )

        rows.append({"app": args.app, "date": stamp, "commit": sha[:12], **metrics})
        print(f"[ok] {stamp} {sha[:8]} SM={metrics['shared_memory_pct']}% MP={metrics['message_passing_pct']}%")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "app",
                "date",
                "commit",
                "primitives_total",
                "shared_memory_pct",
                "message_passing_pct",
                "goroutine_sites",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"[done] {len(rows)} 个快照 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
