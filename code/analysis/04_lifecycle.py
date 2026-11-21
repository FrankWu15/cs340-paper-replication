#!/usr/bin/env python3
"""04_lifecycle.py —— 复现论文 Figure 4「Bug Life Time」的 CDF。

论文原文（ASPLOS'19, §3.2 Figure 4）只给了一句图注：
    "The CDF of the life time of all shared-memory bugs and all message-passing bugs."
没有写 life time 怎么算。本脚本采用的算子（报告里必须声明）：

    life time = fix commit 的提交时间  −  引入该 bug 的 commit 的提交时间

引入提交用 B-SZZ 近似：把修复提交所修改/删除的**旧行**，在 `fix^` 上做
`git blame`，取这些行里**最早**的那次改动所在提交。纯新增的补丁（只加行、
不改旧行）无法定位引入点，记为 no_old_lines 并排除，不做插值。

输出：
    data/bug_lifetime.csv    每条 bug 的 fix / intro / lifetime
    data/lifecycle_cdf.csv   CDF 的采样点（便于画图与复核）
    report/figures/fig4_bug_lifetime.svg

用法：
    python 04_lifecycle.py --repos <6app 目录> --data data/bugs_master.csv \
        --out-dir data --fig report/figures/fig4_bug_lifetime.svg
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
import sys
from pathlib import Path

APPS = ["boltdb", "docker", "etcd", "grpc-go", "kubernetes", "cockroachdb"]
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
BLAME_HEAD = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: (\d+))?$")


def git(repo: Path, *args: str, timeout: int = 180) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)[:60]} -> {r.stderr.strip()[:160]}")
    return r.stdout


def commit_time(repo: Path, rev: str) -> int:
    return int(git(repo, "show", "-s", "--format=%ct", rev).strip())


def is_partial(repo: Path) -> bool:
    """tree:0 / blob:none 的按需克隆：本地没有树或文件内容，blame 会去联网抓包。

    离线环境下这种仓库不能做 SZZ，直接标 repo_partial，避免每条卡 3 分钟超时。
    """
    try:
        filt = git(repo, "config", "--get", "remote.origin.partialclonefilter").strip()
        promisor = git(repo, "config", "--get", "remote.origin.promisor").strip()
    except RuntimeError:
        return False
    return bool(filt) or promisor.lower() == "true"


def changed_files(repo: Path, parent: str, fix: str) -> list[tuple[str, str, str]]:
    """返回 [(status, old_path, new_path)]，只保留改动旧行的情形。"""
    out = git(repo, "diff-tree", "-r", "--no-commit-id", "--name-status", "-M", parent, fix)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            st, path = parts
            rows.append((st[0], path, path))
        elif len(parts) == 3:
            st, old, new = parts
            rows.append((st[0], old, new))
    return rows


def old_ranges(repo: Path, parent: str, fix: str, path: str, deleted: bool) -> list[tuple[int, int]]:
    """补丁在父版本文件里覆盖的行区间 [(start, count)]。

    count == 0 表示纯插入：改为取插入点前一行（start，最小 1）作为上下文代理，
    该行的 blame 时间给出「这段代码所在位置有多老」，是引入时间的上界。
    """
    if deleted:
        n = len(blame(repo, parent, path))
        return [(1, n)] if n else []
    try:
        diff = git(repo, "diff", "-U0", "--no-color", parent, fix, "--", path)
    except RuntimeError:
        return []
    out = []
    for line in diff.splitlines():
        m = HUNK.match(line)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        out.append((start, count))
    return out


_blame_cache: dict[tuple[str, str], list[tuple[str, int]]] = {}


def blame(repo: Path, rev: str, path: str) -> list[tuple[str, int]]:
    """按行返回 [(commit, committer_time)]，下标 0 对应第 1 行。"""
    key = (str(repo), f"{rev}:{path}")
    if key in _blame_cache:
        return _blame_cache[key]
    try:
        out = git(repo, "blame", "--line-porcelain", "-w", rev, "--", path, timeout=600)
    except RuntimeError:
        _blame_cache[key] = []
        return []
    lines: dict[int, tuple[str, int]] = {}
    times: dict[str, int] = {}
    cur_sha, cur_final, pending = None, None, 0
    for line in out.splitlines():
        m = BLAME_HEAD.match(line)
        if m:
            cur_sha, cur_final = m.group(1), int(m.group(3))
            continue
        if line.startswith("committer-time "):
            times[cur_sha] = int(line.split(" ", 1)[1])
            continue
        if line.startswith("\t") and cur_final is not None:
            lines[cur_final] = (cur_sha, times.get(cur_sha, 0))
    ordered = [lines.get(i + 1, ("", 0)) for i in range(len(lines))]
    _blame_cache[key] = ordered
    return ordered


def analyse(repo: Path, fix: str) -> dict:
    """返回 {status, intro_commit, intro_time, fix_time}。"""
    try:
        parent = git(repo, "rev-parse", f"{fix}^").strip()
    except RuntimeError:
        return {"status": "no_parent"}
    fix_time = commit_time(repo, fix)
    best = None      # 真实旧行：(time, commit)
    best_ctx = None  # 纯插入的上下文代理
    scanned = 0
    for status, old, _new in changed_files(repo, parent, fix):
        if status not in ("M", "D", "R", "T"):
            continue
        lines = blame(repo, parent, old)
        if not lines:
            continue
        for start, count in old_ranges(repo, parent, fix, old, status == "D"):
            if count == 0:  # 纯插入：拿插入点前一行做代理
                ln = max(1, start)
                if 1 <= ln <= len(lines):
                    sha, t = lines[ln - 1]
                    if sha and t and (best_ctx is None or t < best_ctx[0]):
                        best_ctx = (t, sha)
                continue
            for ln in range(start, start + count):
                if 1 <= ln <= len(lines):
                    sha, t = lines[ln - 1]
                    if not sha or not t:
                        continue
                    scanned += 1
                    if best is None or t < best[0]:
                        best = (t, sha)
    method = "blame"
    if best is None:
        best, method = best_ctx, "context"
    if best is None:
        return {"status": "no_old_lines"}
    if best[0] > fix_time:
        return {"status": "intro_after_fix"}
    return {"status": "ok", "intro_commit": best[1], "intro_time": best[0],
            "fix_time": fix_time, "scanned_lines": scanned, "method": method}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True, type=Path)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--fig", type=Path)
    ap.add_argument("--apps", default=",".join(APPS))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fig-only", action="store_true", help="跳过 SZZ，只按已有 CSV 重画")
    args = ap.parse_args()

    if args.fig_only:
        write_cdf(args.out_dir / "bug_lifetime.csv", args.fig, args.out_dir)
        return 0

    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    rows = list(csv.DictReader(open(args.data, encoding="utf-8-sig")))
    todo = [r for r in rows if r["app"] in apps and r.get("fix_commit")]
    partial = {a for a in apps if is_partial(args.repos / a)}
    if partial:
        print(f"skip (partial clone, no local blobs): {sorted(partial)}", flush=True)
    if args.limit:
        todo = todo[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "bug_lifetime.csv"
    fields = ["uid", "app", "behavior", "cause_group", "fix_commit", "fix_date",
              "intro_commit", "intro_date", "lifetime_days", "method", "status",
              "scanned_lines"]
    done = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(todo, 1):
            app, fix = r["app"], r["fix_commit"].strip()
            repo = args.repos / app
            rec = {"uid": r["uid"], "app": app, "behavior": r["behavior"],
                   "cause_group": r["cause_group"], "fix_commit": fix}
            if app in partial:
                rec["status"] = "repo_partial"
                w.writerow(rec)
                continue
            try:
                res = analyse(repo, fix)
            except subprocess.TimeoutExpired:
                res = {"status": "timeout"}
            except Exception as exc:  # noqa: BLE001
                res = {"status": f"error:{type(exc).__name__}"}
            rec["status"] = res["status"]
            if res["status"] == "ok":
                rec["fix_date"] = _date(res["fix_time"])
                rec["intro_commit"] = res["intro_commit"]
                rec["intro_date"] = _date(res["intro_time"])
                rec["lifetime_days"] = round((res["fix_time"] - res["intro_time"]) / 86400, 1)
                rec["scanned_lines"] = res["scanned_lines"]
                rec["method"] = res.get("method", "blame")
                done += 1
            w.writerow(rec)
            fh.flush()
            print(f"[{i}/{len(todo)}] {r['uid'][:28]:30} {rec['status']:14} "
                  f"{rec.get('lifetime_days','')}", flush=True)
    print(f"\nok={done}/{len(todo)} -> {out_path}")

    if args.fig:
        write_cdf(out_path, args.fig, args.out_dir)
    return 0


def _date(ts: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")


def write_cdf(csv_path: Path, fig: Path, out_dir: Path) -> None:
    rows = [r for r in csv.DictReader(open(csv_path, encoding="utf-8")) if r["status"] == "ok"]
    groups = {"shared_memory": [], "message_passing": []}
    for r in rows:
        groups[r["cause_group"]].append(float(r["lifetime_days"]))
    for k in groups:
        groups[k].sort()

    x_max = int(min(1200, max(700, math.ceil(max([0] + [v for vs in groups.values() for v in vs]) / 100.0) * 100)))
    pts = {}
    for k, vs in groups.items():
        if not vs:
            continue
        n = len(vs)
        curve = [(0, 0.0)]
        for i, v in enumerate(vs, 1):
            xx = min(v, x_max)
            curve.append((xx, i / n))
        curve.append((x_max, 1.0))
        pts[k] = (curve, n)

    # 采样成 CSV，便于复核
    with open(out_dir / "lifecycle_cdf.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "shared_memory_cdf", "message_passing_cdf"])
        for d in range(0, x_max + 1, 10):
            row = [d]
            for k in ("shared_memory", "message_passing"):
                c = pts.get(k)
                if not c:
                    row.append("")
                    continue
                val = 0.0
                for xx, yy in c[0]:
                    if xx <= d:
                        val = yy
                row.append(round(val, 4))
            w.writerow(row)

    fig.parent.mkdir(parents=True, exist_ok=True)
    svg = render_svg(pts, x_max)
    fig.write_text(svg, encoding="utf-8")
    print(f"figure -> {fig}")


PAPER = {
    "shared_memory": [0.039, 0.660, 0.780, 0.898, 0.939, 0.979, 0.979, 1.000],
    "message_passing": [0.014, 0.523, 0.769, 0.861, 0.892, 0.969, 0.969, 1.000],
}


def render_svg(pts, x_max: int) -> str:
    W, H = 760, 430
    L, R, T, B = 90, 720, 70, 350  # 绘图区
    def sx(x): return L + (R - L) * x / max(1, x_max)
    def sy(y): return B - (B - T) * y

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           'font-family="Helvetica,Arial,sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="30" y="34" font-size="17" font-weight="bold" fill="#1a202c">'
           'Figure 4. Bug life time: CDF by cause group</text>',
           f'<text x="30" y="55" font-size="12" fill="#4a5568">'
           'life time = fix commit date - bug-introducing commit date (B-SZZ, first parent)</text>']

    # y grid
    for i in range(6):
        v = i / 5
        y = sy(v)
        out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        out.append(f'<text x="{L-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#4a5568">'
                   f'{v:g}</text>')
    for d in range(0, x_max + 1, 100):
        x = sx(d)
        out.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{B}" stroke="#edf2f7" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{B+18}" text-anchor="middle" font-size="11" fill="#4a5568">{d}</text>')
    out.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="#a0aec0" stroke-width="1.2"/>')
    out.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{B}" stroke="#a0aec0" stroke-width="1.2"/>')
    out.append(f'<text x="{(L+R)/2:.0f}" y="{B+38}" text-anchor="middle" font-size="12" fill="#2d3748">'
               'Bug Life Time (Days)</text>')
    out.append(f'<text x="24" y="{(T+B)/2:.0f}" text-anchor="middle" font-size="12" fill="#2d3748" '
               f'transform="rotate(-90 24 {(T+B)/2:.0f})">Percentage of Studied Bugs</text>')

    colors = {"shared_memory": "#c53030", "message_passing": "#2b6cb0"}
    labels = {"shared_memory": "shared memory", "message_passing": "message passing"}

    # 论文原图（从 PDF 矢量路径反解，每 100 天一个采样点）作为虚线参考
    for k, vals in PAPER.items():
        d = f'M {sx(0):.1f} {sy(vals[0]):.1f} '
        d += " ".join(f'L {sx(i*100):.1f} {sy(v):.1f}' for i, v in enumerate(vals) if i)
        out.append(f'<path d="{d}" fill="none" stroke="{colors[k]}" stroke-width="1.4" '
                   'stroke-dasharray="5 4" opacity="0.55"/>')
    for idx, (k, (curve, n)) in enumerate(pts.items()):
        d = f'M {sx(curve[0][0]):.1f} {sy(curve[0][1]):.1f} '
        d += " ".join(f'L {sx(x):.1f} {sy(y):.1f}' for x, y in curve[1:])
        out.append(f'<path d="{d}" fill="none" stroke="{colors[k]}" stroke-width="2.4" '
                   'stroke-linejoin="round"/>')
        ly = B - 34 - 22 * idx
        out.append(f'<line x1="{R-200}" y1="{ly}" x2="{R-170}" y2="{ly}" stroke="{colors[k]}" stroke-width="2.4"/>')
        out.append(f'<text x="{R-162}" y="{ly+4}" font-size="12" fill="#2d3748">{labels[k]} (n={n})</text>')

    out.append(f'<text x="30" y="{H-14}" font-size="11" fill="#718096">'
               f'solid = ours (data/bug_lifetime.csv) · dashed = paper Fig.4 digitized from PDF · '
               f'shared memory n={pts.get("shared_memory",(0,0))[1]}, '
               f'message passing n={pts.get("message_passing",(0,0))[1]}</text>')
    out.append('</svg>')
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
