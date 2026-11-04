#!/usr/bin/env python3
"""P6 阶段：从标注数据生成论文的交叉表、lift 相关性与 bug 生命周期 CDF。

输入 data/bugs.csv，列：
    bug_id, app, behavior, cause, fix_strategy, fix_primitive,
    introduced_date, fixed_date
（behavior ∈ {blocking, non-blocking}；cause 见 config/apps.yaml 的 labels）

产出：
    out/tables.md        可直接贴进报告的表（Table 5/6/7/9/10/11 的等价物）
    out/lift.csv         lift 矩阵
    out/lifetime.csv     bug 生命周期样本
    out/fig4_lifetime.png  若安装了 matplotlib

用法:
    python scripts/04_stats_figures.py --bugs data/bugs.csv --outdir out
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from collections import Counter, defaultdict
from pathlib import Path

# 论文的"致因"第二维度：只分两组
MP_CAUSES = {
    "chan",
    "chan_w_other",
    "chan with other",
    "chan_with_other",
    "messaging_lib",
    "pipe",
    "context",
    "library",
    "lib",
}


def cause_group(cause: str) -> str:
    return "message_passing" if cause.strip().lower() in MP_CAUSES else "shared_memory"


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("bug_id")]


def md_table(headers: list[str], rows: list[list], title: str = "") -> str:
    lines = []
    if title:
        lines += [f"### {title}", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    lines.append("")
    return "\n".join(lines)


def crosstab(rows: list[dict], row_key, col_key, row_label: str, col_label: str) -> str:
    cols = sorted({col_key(r) for r in rows})
    table: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        table[row_key(r)][col_key(r)] += 1

    out_rows = []
    col_totals = Counter()
    for rk in sorted(table):
        cells = [table[rk][c] for c in cols]
        col_totals.update(table[rk])
        out_rows.append([rk] + cells + [sum(cells)])
    out_rows.append(["**Total**"] + [col_totals[c] for c in cols] + [len(rows)])
    headers = [row_label] + cols + ["Total"]
    return md_table(headers, out_rows, f"{row_label} × {col_label}")


def lift_matrix(rows: list[dict], row_key, col_key, min_support: int = 10) -> tuple[str, list[list]]:
    n = len(rows)
    ra = Counter(row_key(r) for r in rows)
    cb = Counter(col_key(r) for r in rows)
    ab = Counter((row_key(r), col_key(r)) for r in rows)

    rows_kept = [a for a, c in ra.items() if c >= min_support]
    cols_kept = sorted(cb)
    matrix = []
    for a in sorted(rows_kept):
        line = []
        for b in cols_kept:
            p_ab = ab[(a, b)] / n
            denom = (ra[a] / n) * (cb[b] / n)
            line.append(round(p_ab / denom, 2) if denom else 0.0)
        matrix.append([a, ra[a]] + line)

    headers = ["cause (n≥%d)" % min_support, "n"] + cols_kept
    return md_table(headers, matrix, "lift(cause, fix)"), matrix


def lifetime(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        intro, fixed = r.get("introduced_date", ""), r.get("fixed_date", "")
        if not intro or not fixed:
            continue
        try:
            d0 = dt.date.fromisoformat(intro[:10])
            d1 = dt.date.fromisoformat(fixed[:10])
        except ValueError:
            continue
        out.append(
            {
                "bug_id": r["bug_id"],
                "group": cause_group(r.get("cause", "")),
                "days": (d1 - d0).days,
            }
        )
    return out


def write_cdf(samples: list[dict], outdir: Path) -> None:
    with (outdir / "lifetime.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["bug_id", "group", "days"])
        w.writeheader()
        w.writerows(samples)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[!] 未安装 matplotlib，跳过 Fig 4 绘图（CSV 已写出）")
        return

    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for group in ("shared_memory", "message_passing"):
        vals = sorted(s["days"] for s in samples if s["group"] == group)
        if not vals:
            continue
        ys = [(i + 1) / len(vals) for i in range(len(vals))]
        ax.step(vals, ys, where="post", label=group.replace("_", " "))
    ax.set_xlabel("Bug life time (days)")
    ax.set_ylabel("Percentage of studied bugs")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(outdir / "fig4_lifetime.png", dpi=200)
    print(f"[ok] {outdir / 'fig4_lifetime.png'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bugs", default="data/bugs.csv")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--min-support", type=int, default=10, help="lift 只统计样本量≥该值的类别")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = load(Path(args.bugs))
    if not rows:
        print("[x] 没有数据")
        return 2

    parts = ["# 统计结果（由 scripts/04_stats_figures.py 生成）", ""]
    parts.append(f"样本数：{len(rows)}")
    parts.append("")

    # Table 5 等价物：app × behavior，app × cause 分组
    parts.append(crosstab(rows, lambda r: r["app"], lambda r: r["behavior"], "Application", "Behavior"))
    parts.append(crosstab(rows, lambda r: r["app"], lambda r: cause_group(r["cause"]), "Application", "Cause"))

    # blocking / non-blocking 分开做致因 × 修复策略
    for beh in ("blocking", "non-blocking"):
        sub = [r for r in rows if r["behavior"] == beh]
        if not sub:
            continue
        parts.append(crosstab(sub, lambda r: r["cause"], lambda r: r["fix_strategy"], f"{beh} cause", "fix strategy"))
        parts.append(
            crosstab(sub, lambda r: r["cause"], lambda r: r["fix_primitive"], f"{beh} cause", "fix primitive")
        )
        text, matrix = lift_matrix(sub, lambda r: r["cause"], lambda r: r["fix_strategy"], args.min_support)
        parts.append(text)
        with (outdir / f"lift_{beh}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["cause", "n", "fix_strategy_lift...", ""])
            for line in matrix:
                w.writerow(line)

    # 简单校验：论文的核心比例
    n = len(rows)
    block = sum(1 for r in rows if r["behavior"] == "blocking")
    mp_block = sum(1 for r in rows if r["behavior"] == "blocking" and cause_group(r["cause"]) == "message_passing")
    mp_all = sum(1 for r in rows if cause_group(r["cause"]) == "message_passing")
    parts.append("## 核心比例校验")
    parts.append("")
    parts.append(f"- blocking: {block}/{n} = {100*block/n:.1f}%（论文 85/171 = 49.7%）")
    if block:
        parts.append(f"- blocking 中 message passing 致因: {mp_block}/{block} = {100*mp_block/block:.1f}%（论文 58%）")
    parts.append(f"- 全部 bug 中 message passing 致因: {mp_all}/{n} = {100*mp_all/n:.1f}%（论文 66/171 = 38.6%）")
    parts.append("")

    samples = lifetime(rows)
    if samples:
        groups = defaultdict(list)
        for s in samples:
            groups[s["group"]].append(s["days"])
        parts.append("## Bug 生命周期（Fig 4 输入）")
        parts.append("")
        parts.append("| 分组 | 样本 | 中位数(天) | 均值(天) |")
        parts.append("|---|---|---|---|")
        for g, vals in sorted(groups.items()):
            vals.sort()
            med = vals[len(vals) // 2]
            parts.append(f"| {g} | {len(vals)} | {med} | {sum(vals)/len(vals):.0f} |")
        parts.append("")
        write_cdf(samples, outdir)
    else:
        parts.append("> 缺少 introduced_date / fixed_date，无法画生命周期 CDF。")
        parts.append("> 引入时间可用 `git log -S'<修复改动的关键行>' --reverse` 或 `git blame <fix>^` 反查。")
        parts.append("")

    (outdir / "tables.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"[ok] {outdir / 'tables.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
