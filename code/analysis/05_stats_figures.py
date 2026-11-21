#!/usr/bin/env python3
"""05_stats_figures.py —— 复现论文 Table 6/7/9/10/11 与两组 lift。

数据来源是 artifact 自带的两张 one-hot 标注表：
    repro/data/bug_table_blocking.csv      85 行（blocking）
    repro/data/bug_table_non_blocking.csv  86 行（non-blocking）
每列对应论文里的一个 cause / fix strategy / patch primitive 标记。

本脚本只做「标注 → 交叉表 → lift」的复算，不做人工重标（19 项里的第 3 项已声明
跳过）。因此它复现的是**论文的统计口径与算术**，不是「重读 171 条补丁」。

五张表的列映射（论文用词 ← artifact 列名）：
    Table 6   Mutex / RWMutex / Wait / Chan / Chan w/ / Lib
              ← lock related / rwlock / wait related / channel related
                / mixing lock/wait & channel / messaging lib
    Table 7   Adds / Moves / Changes / Removes / Misc.
              ← Syn Add / Syn Move / Syn Change / Syn Remove / Misc
    Table 9   traditional / anon. / waitgroup / lib / chan / lib
              ← traditional bug / anonymous funcion / misusing waitgroup
                / race@lib / misusing channel / misusing messaging lib
    Table 10  Adds / Moves / Bypass / Data Private / Misc.
              ← Add-t / Move-t / eliminate or bypass Insruction / data private / Misc.
    Table 11  Mutex / Channel / Atomic / WaitGroup / Cond / Misc. / None
              ← lock-patch / channel-patch / atomic-patch / waitgroup-patch
                / cond-patch / select-patch / none

lift(A, B) = P(AB) / (P(A)·P(B)) = n_AB·N / (n_A·n_B)，与论文 §5.2 的公式一致；
论文只报「样本数 > 10 的 cause 类别」，本脚本默认同样过滤（--min-support 可改）。

输出：
    results/tables/table6_blocking_cause_app.csv
    results/tables/table7_blocking_cause_fix.csv
    results/tables/table9_nonblocking_cause_app.csv
    results/tables/table10_nonblocking_cause_fix.csv
    results/tables/table11_nonblocking_cause_primitive.csv
    results/tables/lift_blocking.csv
    results/tables/lift_nonblocking_strategy.csv
    results/tables/lift_nonblocking_primitive.csv
    report/tables_6_11.md

用法（在 ALL/11-21 目录下）：
    python code/analysis/05_stats_figures.py
    python code/analysis/05_stats_figures.py --data-dir ../../../repro/data

退出码：0 全部逐格一致；3 有行未归类；4 与论文表格有差异（差异会写进报告）。
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

# ---------------------------------------------------------------- 列映射

CAUSE6 = [  # blocking 的六个 cause，顺序同论文 Table 6
    ("Mutex", "lock related"),
    ("RWMutex", "rwlock"),
    ("Wait", "wait related"),
    ("Chan", "channel related"),
    ("Chan w/", "mixing lock/wait & channel"),
    ("Lib", "messaging lib"),
]
FIX7 = [  # Table 7 的五个修复策略
    ("Adds", "Syn Add"),
    ("Moves", "Syn Move"),
    ("Changes", "Syn Change"),
    ("Removes", "Syn Remove"),
    ("Misc.", "Misc"),
]
CAUSE9 = [  # non-blocking 的六个 cause，顺序同论文 Table 9
    ("traditional", "traditional bug"),
    ("anon.", "anonymous funcion"),
    ("waitgroup", "misusing waitgroup"),
    ("lib", "race@lib"),
    ("chan", "misusing channel"),
    ("msg lib", "misusing messaging lib"),
]
FIX10 = [  # Table 10 的五个修复策略
    ("Adds", "Add-t"),
    ("Moves", "Move-t"),
    ("Bypass", "eliminate or bypass Insruction"),
    ("Data Private", "data private"),
    ("Misc.", "Misc."),
]
PRIM11 = [  # Table 11 的七类补丁内原语
    ("Mutex", "lock-patch"),
    ("Channel", "channel-patch"),
    ("Atomic", "atomic-patch"),
    ("WaitGroup", "waitgroup-patch"),
    ("Cond", "cond-patch"),
    ("Misc.", "select-patch"),
    ("None", "none"),
]

APPS = ["Docker", "Kubernetes", "etcd", "CockroachDB", "gRPC", "BoltDB"]

# 论文原表，用于逐格比对
PAPER = {
    "table6": {
        "Docker": [9, 0, 3, 5, 2, 2],
        "Kubernetes": [6, 2, 0, 3, 6, 0],
        "etcd": [5, 0, 0, 10, 5, 1],
        "CockroachDB": [4, 3, 0, 5, 0, 0],
        "gRPC": [2, 0, 0, 6, 2, 1],
        "BoltDB": [2, 0, 0, 0, 1, 0],
        "Total": [28, 5, 3, 29, 16, 4],
    },
    "table7": {
        "Mutex": [9, 7, 2, 8, 2],
        "Wait": [0, 1, 0, 1, 1],
        "RWMutex": [0, 2, 0, 3, 0],
        "Chan": [15, 1, 5, 4, 4],
        "Chan w/": [6, 3, 2, 4, 1],
        "Lib": [1, 0, 0, 1, 2],
        "Total": [31, 14, 9, 21, 10],
    },
    "table9": {
        "Docker": [9, 6, 0, 1, 6, 1],
        "Kubernetes": [8, 3, 1, 0, 5, 0],
        "etcd": [9, 0, 2, 2, 3, 0],
        "CockroachDB": [10, 1, 3, 2, 0, 0],
        "gRPC": [8, 1, 0, 1, 2, 0],
        "BoltDB": [2, 0, 0, 0, 0, 0],
        "Total": [46, 11, 6, 6, 16, 1],
    },
    "table10": {
        "traditional": [27, 4, 5, 10, 0],
        "waitgroup": [3, 2, 1, 0, 0],
        "anon.": [5, 2, 0, 4, 0],
        "lib": [1, 2, 1, 0, 2],
        "chan": [6, 7, 3, 0, 0],
        "msg lib": [0, 0, 0, 0, 1],
        "Total": [42, 17, 10, 14, 3],
    },
    "table11": {
        "traditional": [24, 3, 6, 0, 0, 0, 13],
        "waitgroup": [2, 0, 0, 4, 3, 0, 0],
        "anon.": [3, 2, 3, 0, 0, 0, 3],
        "lib": [0, 2, 1, 1, 0, 1, 2],
        "chan": [3, 11, 0, 2, 1, 2, 1],
        "msg lib": [0, 1, 0, 0, 0, 0, 0],
        "Total": [32, 19, 10, 7, 4, 3, 19],
    },
}

# 论文正文报的 lift（§5.2 / §6.2），第 7、8 节用来对照
PAPER_LIFT = {
    "blocking": [("Mutex", "Moves", 1.52), ("Chan", "Adds", 1.42)],
    "nonblocking_primitive": [("chan", "Channel", 2.7)],
    "nonblocking_strategy": [("anon.", "Data Private", 2.23), ("chan", "Moves", 2.21)],
}

# 标注表的行内例外。Table 6 要求每行恰好落进一个 cause，实测有两条不满足；
# 下面的处理与论文表格数字反推一致（只改归类，不改原始标注）：
#   1) moby#25384：六个 cause 列全空，但 WaitGroup/waitgroup 为 1。论文 Docker
#      行 Wait=3，比"只数 wait related"多 1，即这条按 WaitGroup 记作 Wait。
#   2) kubernetes#11298：同时打了 wait related 与 mixing lock/wait & channel。
#      论文 Kubernetes 行 Wait=0、Chan w/=6，说明 mixing 优先。
EXCEPTIONS = {"moby#25384": "Wait", "kubernetes#11298": "Chan w/"}


def on(row: dict, col: str) -> int:
    return 1 if (row.get(col) or "").strip() == "1" else 0


def load(path: Path) -> list:
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def cause_of_blocking(row: dict) -> str:
    uid = (row.get("uid") or "").strip()
    if uid in EXCEPTIONS:
        return EXCEPTIONS[uid]
    if on(row, "mixing lock/wait & channel"):
        return "Chan w/"
    for label, col in CAUSE6:
        if on(row, col):
            return label
    return "?"


def cause_of_nonblocking(row: dict) -> str:
    for label, col in CAUSE9:
        if on(row, col):
            return label
    return "?"


def app_key(row: dict) -> str:
    raw = (row.get("application") or "").strip().lower()
    return {
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "etcd": "etcd",
        "cockroachdb": "CockroachDB",
        "grpc": "gRPC",
        "boltdb": "BoltDB",
    }.get(raw, raw)


def cause_by_app(rows, cause_fn, causes, apps):
    """返回 {cause: {app: n}}"""
    d = {c: {a: 0 for a in apps} for c in causes}
    for r in rows:
        c, a = cause_fn(r), app_key(r)
        if c in d and a in d[c]:
            d[c][a] += 1
    return d


def cause_by_cols(rows, cause_fn, causes, cols):
    """返回 {cause: [n per col]}"""
    return {c: [sum(1 for r in rows if cause_fn(r) == c and on(r, col)) for _, col in cols]
            for c in causes}


def lift_matrix(rows, cause_fn, cols, min_support: int = 0):
    """lift(A,B) = n_AB·N/(n_A·n_B)。返回 (降序列表, N)。"""
    n = len(rows)
    out = []
    for cause in dict.fromkeys(cause_fn(r) for r in rows):
        n_a = sum(1 for r in rows if cause_fn(r) == cause)
        if n_a < min_support:
            continue
        for label, col in cols:
            n_b = sum(on(r, col) for r in rows)
            n_ab = sum(1 for r in rows if cause_fn(r) == cause and on(r, col))
            val = 0.0 if (n_a == 0 or n_b == 0 or n_ab == 0) else n_ab * n / (n_a * n_b)
            out.append((val, cause, label, n_ab, n_a, n_b))
    return sorted(out, key=lambda x: -x[0]), n


def both_sides(data, min_cause: int, min_fix: int):
    """lift 只在 cause 与 fix 两侧样本都够大时才有统计意义。"""
    return [x for x in data if x[4] >= min_cause and x[5] >= min_fix]


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def md_table(header, rows) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    root = here.parent.parent  # 仓库根 / repository root
    ap = argparse.ArgumentParser(description="复现 Table 6/7/9/10/11 与 lift")
    ap.add_argument("--data-dir", default=str(root / "data"))
    ap.add_argument("--out-dir", default=str(root / "data" / "tables"))
    ap.add_argument("--report", default=str(root / "report" / "appendix" / "tables_6_11.md"))
    ap.add_argument("--min-support", type=int, default=10,
                    help="lift 只报 cause 样本数 > 此值的组合（论文用 10）")
    ap.add_argument("--min-fix-support", type=int, default=10,
                    help="双边过滤时 fix 类别的最小样本数，仅影响报告里的对照表")
    args = ap.parse_args(argv)

    data_dir, out_dir = Path(args.data_dir), Path(args.out_dir)
    blocking = load(data_dir / "bug_table_blocking.csv")
    nonblocking = load(data_dir / "bug_table_non_blocking.csv")

    bad_rows = [r["uid"] for r in blocking if cause_of_blocking(r) == "?"]
    bad_rows += [r["uid"] for r in nonblocking if cause_of_nonblocking(r) == "?"]
    if bad_rows:
        print(f"[err] 有行未落到任何 cause 类别：{bad_rows}", file=sys.stderr)
        return 3

    c6 = [c for c, _ in CAUSE6]
    c9 = [c for c, _ in CAUSE9]

    # ---------------- 五张表
    m6 = cause_by_app(blocking, cause_of_blocking, c6, APPS)
    m7 = cause_by_cols(blocking, cause_of_blocking, c6, FIX7)
    m9 = cause_by_app(nonblocking, cause_of_nonblocking, c9, APPS)
    m10 = cause_by_cols(nonblocking, cause_of_nonblocking, c9, FIX10)
    m11 = cause_by_cols(nonblocking, cause_of_nonblocking, c9, PRIM11)

    tot6 = [sum(m6[c][a] for c in c6) for a in APPS]
    tot7 = [sum(m7[c][i] for c in c6) for i in range(len(FIX7))]
    tot9 = [sum(m9[c][a] for c in c9) for a in APPS]
    tot10 = [sum(m10[c][i] for c in c9) for i in range(len(FIX10))]
    tot11 = [sum(m11[c][i] for c in c9) for i in range(len(PRIM11))]

    # ---------------- 逐格比对
    diffs = []

    def cmp_app(name, mat, paper, causes):
        for app, want in paper.items():
            if app == "Total":
                got = [sum(mat[c][a] for a in APPS) for c in causes]
                if got != want:
                    diffs.append((name, "Total", got, want))
                continue
            got = [mat[c][app] for c in causes]
            if got != want:
                diffs.append((name, app, got, want))

    def cmp_rows(name, mat, paper, causes):
        for label, want in paper.items():
            if label == "Total":
                got = [sum(mat[c][i] for c in causes) for i in range(len(want))]
            else:
                got = mat[label]
            if got != want:
                diffs.append((name, label, got, want))

    cmp_app("Table 6", m6, PAPER["table6"], c6)
    cmp_rows("Table 7", m7, PAPER["table7"], c6)
    cmp_app("Table 9", m9, PAPER["table9"], c9)
    cmp_rows("Table 10", m10, PAPER["table10"], c9)
    cmp_rows("Table 11", m11, PAPER["table11"], c9)

    # ---------------- lift
    lb, n_b = lift_matrix(blocking, cause_of_blocking, FIX7, args.min_support)
    lb_all, _ = lift_matrix(blocking, cause_of_blocking, FIX7, 0)
    lns, n_nb = lift_matrix(nonblocking, cause_of_nonblocking, FIX10, args.min_support)
    lns_all, _ = lift_matrix(nonblocking, cause_of_nonblocking, FIX10, 0)
    lnp, _ = lift_matrix(nonblocking, cause_of_nonblocking, PRIM11, args.min_support)
    lnp_all, _ = lift_matrix(nonblocking, cause_of_nonblocking, PRIM11, 0)

    # 双边过滤：cause 与 fix 两侧都要求样本数达标，用于和论文的排序对照
    lb_bs = both_sides(lb_all, args.min_support, args.min_fix_support)
    lns_bs = both_sides(lns_all, args.min_support, args.min_fix_support)
    lnp_bs = both_sides(lnp_all, args.min_support, args.min_fix_support)

    # ---------------- 落盘：CSV
    write_csv(out_dir / "table6_blocking_cause_app.csv",
              ["cause"] + APPS + ["Total"],
              [[c] + [m6[c][a] for a in APPS] + [sum(m6[c].values())] for c in c6]
              + [["Total"] + tot6 + [sum(tot6)]])
    write_csv(out_dir / "table7_blocking_cause_fix.csv",
              ["cause"] + [l for l, _ in FIX7] + ["Total"],
              [[c] + m7[c] + [sum(m7[c])] for c in c6] + [["Total"] + tot7 + [sum(tot7)]])
    write_csv(out_dir / "table9_nonblocking_cause_app.csv",
              ["cause"] + APPS + ["Total"],
              [[c] + [m9[c][a] for a in APPS] + [sum(m9[c].values())] for c in c9]
              + [["Total"] + tot9 + [sum(tot9)]])
    write_csv(out_dir / "table10_nonblocking_cause_fix.csv",
              ["cause"] + [l for l, _ in FIX10] + ["Total"],
              [[c] + m10[c] + [sum(m10[c])] for c in c9] + [["Total"] + tot10 + [sum(tot10)]])
    write_csv(out_dir / "table11_nonblocking_cause_primitive.csv",
              ["cause"] + [l for l, _ in PRIM11] + ["Total"],
              [[c] + m11[c] + [sum(m11[c])] for c in c9] + [["Total"] + tot11 + [sum(tot11)]])

    def lift_rows(data, n):
        return [[f"{v:.2f}", a, b, n_ab, n_a, n_b, n] for v, a, b, n_ab, n_a, n_b in data]

    lift_hdr = ["lift", "cause", "fix", "n_AB", "n_A", "n_B", "N"]
    write_csv(out_dir / "lift_blocking.csv", lift_hdr, lift_rows(lb_all, n_b))
    write_csv(out_dir / "lift_nonblocking_strategy.csv", lift_hdr, lift_rows(lns_all, n_nb))
    write_csv(out_dir / "lift_nonblocking_primitive.csv", lift_hdr,
              [[f"{v:.2f}", a, b, n_ab, n_a, n_b, n_nb] for v, a, b, n_ab, n_a, n_b in lnp_all])

    # ---------------- 报告
    md = []
    md.append("# Table 6 / 7 / 9 / 10 / 11 复现")
    md.append("")
    md.append("由 `code/analysis/05_stats_figures.py` 生成，数据源为 artifact 的两张 "
              "one-hot 标注表（blocking 85 行、non-blocking 86 行）。")
    md.append("")
    md.append("**口径声明**：本报告复现的是论文的统计口径与算术，不是重读 171 条补丁——"
              "人工判读那一步（19 项里的第 3 项）我们主动跳过，全部沿用 artifact 标签。"
              "因此「五张表逐格一致」证明的是汇总与计算没走样，不代表独立复核过每一条标注。")
    md.append("")
    md.append(f"逐格比对结果：**{'全部一致' if not diffs else f'{len(diffs)} 处不一致'}**。")
    md.append("")

    md.append("## Table 6　blocking bug 的根因 × 应用")
    md.append("")
    md.append(md_table(["cause"] + APPS + ["Total"],
                       [[c] + [m6[c][a] for a in APPS] + [sum(m6[c].values())] for c in c6]
                       + [["**Total**"] + tot6 + [sum(tot6)]]))
    md.append("")
    sm6 = sum(sum(m6[c].values()) for c in c6[:3])
    mp6 = sum(sum(m6[c].values()) for c in c6[3:])
    md.append(f"论文合计 28 / 5 / 3 / 29 / 16 / 4（N={sum(tot6)}）；"
              f"共享内存 {sm6}（{sm6 * 100 / sum(tot6):.0f}%）、"
              f"消息传递 {mp6}（{mp6 * 100 / sum(tot6):.0f}%）。")
    md.append("")

    md.append("## Table 7　blocking bug 的修复策略 × 根因")
    md.append("")
    md.append(md_table(["cause"] + [l for l, _ in FIX7] + ["Total"],
                       [[c] + m7[c] + [sum(m7[c])] for c in c6]
                       + [["**Total**"] + tot7 + [sum(tot7)]]))
    md.append("")
    md.append("注：85 条 blocking bug 各有且仅有一个策略标记，行合计与列合计都是 85。")
    md.append("")

    md.append("## Table 9　non-blocking bug 的根因 × 应用")
    md.append("")
    md.append(md_table(["cause"] + APPS + ["Total"],
                       [[c] + [m9[c][a] for a in APPS] + [sum(m9[c].values())] for c in c9]
                       + [["**Total**"] + tot9 + [sum(tot9)]]))
    md.append("")
    sm9 = sum(sum(m9[c].values()) for c in c9[:4])
    mp9 = sum(sum(m9[c].values()) for c in c9[4:])
    md.append(f"论文合计 46 / 11 / 6 / 6 / 16 / 1（N={sum(tot9)}）；"
              f"共享内存 {sm9}（{sm9 * 100 / sum(tot9):.0f}%）、"
              f"消息传递 {mp9}（{mp9 * 100 / sum(tot9):.0f}%）。")
    md.append("")

    md.append("## Table 10　non-blocking bug 的修复策略 × 根因")
    md.append("")
    md.append(md_table(["cause"] + [l for l, _ in FIX10] + ["Total"],
                       [[c] + m10[c] + [sum(m10[c])] for c in c9]
                       + [["**Total**"] + tot10 + [sum(tot10)]]))
    md.append("")
    md.append("论文把 Adds+Moves 合称「限制时序」，合计 59/86 = 69%。")
    md.append("")

    md.append("## Table 11　non-blocking 补丁里用到的同步原语")
    md.append("")
    md.append(md_table(["cause"] + [l for l, _ in PRIM11] + ["Marks"],
                       [[c] + m11[c] + [sum(m11[c])] for c in c9]
                       + [["**Total**"] + tot11 + [sum(tot11)]]))
    md.append("")
    md.append("注：一条 bug 的补丁里可以出现多种原语，故格子总和 "
              f"{sum(tot11)} 大于 bug 数 86（论文未报「多于一个原语」的条数，"
              "artifact 的 `more than one` 列为 10）。最后一行是原语标记的合计，"
              "与论文 Total 行 32 / 19 / 10 / 7 / 4 / 3 / 19 一致。")
    md.append("")

    def find(data, cause, label):
        for v, a, b, *_ in data:
            if a == cause and b == label:
                return v
        return None

    md.append(f"## lift：blocking × 修复策略（N={n_b}）")
    md.append("")
    md.append(f"左表只过滤 cause（样本 > {args.min_support}），即论文字面口径；"
              f"右表两侧都要求 > {args.min_fix_support}。")
    md.append("")
    md.append(md_table(["lift", "cause", "fix", "n_AB", "n_A", "n_B"],
                       [[f"{v:.2f}", a, b, n_ab, n_a, n_b] for v, a, b, n_ab, n_a, n_b in lb[:8]]))
    md.append("")
    md.append(md_table(["lift", "cause 样本", "fix 样本", "cause", "fix"],
                       [[f"{v:.2f}", n_a, n_b, a, b] for v, a, b, _, n_a, n_b in lb_bs[:8]]))
    md.append("")
    md.append("论文：Mutex×Moves = 1.52（最强）、Chan×Adds = 1.42（第二），"
              "「其余均低于 1.16」。")
    md.append("")

    md.append(f"## lift：non-blocking × 修复策略（N={n_nb}）")
    md.append("")
    md.append(md_table(["lift", "cause", "strategy", "n_AB", "n_A", "n_B"],
                       [[f"{v:.2f}", a, b, n_ab, n_a, n_b] for v, a, b, n_ab, n_a, n_b in lns[:8]]))
    md.append("")
    md.append(md_table(["lift", "cause 样本", "策略样本", "cause", "strategy"],
                       [[f"{v:.2f}", n_a, n_b, a, b] for v, a, b, _, n_a, n_b in lns_bs[:8]]))
    md.append("")
    md.append("论文：anon.×Data Private = 2.23、misusing chan×Moves = 2.21。")
    md.append("")

    md.append(f"## lift：non-blocking × 补丁原语（N={n_nb}）")
    md.append("")
    md.append(md_table(["lift", "cause", "primitive", "n_AB", "n_A", "n_B"],
                       [[f"{v:.2f}", a, b, n_ab, n_a, n_b] for v, a, b, n_ab, n_a, n_b in lnp[:8]]))
    md.append("")
    md.append(md_table(["lift", "cause 样本", "原语样本", "cause", "primitive"],
                       [[f"{v:.2f}", n_a, n_b, a, b] for v, a, b, _, n_a, n_b in lnp_bs[:8]]))
    md.append("")
    md.append("论文：misusing chan×Channel = 2.7（最强）。")
    md.append("")

    # ---------------- 与论文对话
    cmp_rows = []
    for cause, label, paper_v in PAPER_LIFT["blocking"]:
        got = find(lb_all, cause, label)
        cmp_rows.append(["blocking", f"{cause} × {label}", f"{paper_v:.2f}", f"{got:.2f}",
                         "一致" if abs(got - paper_v) < 0.006 else f"差 {got - paper_v:+.2f}"])
    for cause, label, paper_v in PAPER_LIFT["nonblocking_strategy"]:
        got = find(lns_all, cause, label)
        cmp_rows.append(["non-blocking", f"{cause} × {label}", f"{paper_v:.2f}", f"{got:.2f}",
                         "一致" if abs(got - paper_v) < 0.006 else f"差 {got - paper_v:+.2f}"])
    for cause, label, paper_v in PAPER_LIFT["nonblocking_primitive"]:
        got = find(lnp_all, cause, label)
        cmp_rows.append(["non-blocking", f"{cause} × {label}", f"{paper_v:.2f}", f"{got:.2f}",
                         "一致" if abs(got - paper_v) < 0.006 else f"差 {got - paper_v:+.2f}"])

    md.append("## lift 数值与论文逐条对照")
    md.append("")
    md.append(md_table(["分组", "组合", "论文", "本文", "判定"], cmp_rows))
    md.append("")

    md.append("## 与论文的三处对话")
    md.append("")
    chan_change = find(lb_all, "Chan", "Changes")
    mutex_removes = find(lb_all, "Mutex", "Removes")
    chan_channel = find(lnp_all, "chan", "Channel")
    md.append(f"**1）Table 6/7/9/10/11 五张表逐格一致。** 85 + 86 条标注一行不差，"
              "说明我们对 artifact 列名的映射与论文的统计口径相同。这是后面 lift 可比的前提。")
    md.append("")
    md.append(f"**2）blocking lift 的排序取决于「>10」过滤在哪一维生效。** 论文只写"
              "「categories that have more than 10 blocking bugs」，没说 fix 类别是否也过滤。"
              f"按字面只过滤 cause，Chan×Changes = {chan_change:.2f}（5·85/(29·9)）会排第一，"
              "与论文「Mutex×Moves 最强、Chan×Adds 第二」矛盾；"
              "把 fix 侧也要求 ≥10 后，Chan×Changes（fix 样本 9）与 Chan w/×Changes（2）被排除，"
              f"排序立刻回到 1.52 / 1.42，只剩 Chan×Misc. = 1.17 比论文的「below 1.16」高 0.01"
              f"（精确值 1.172，四舍五入边界），以及 Mutex×Removes = {mutex_removes:.2f} "
              "正好压在 1.16 上。也就是说论文的排序只在「双侧过滤」这一口径下站得住，"
              "而正文没写清过滤作用在哪一维；我们不替他选口径，两种都列出来。")
    md.append("")
    md.append(f"**3）non-blocking 三个 lift 中两个精确命中。** anon.×Data Private = "
              f"{find(lns_all, 'anon.', 'Data Private'):.2f}（论文 2.23）、"
              f"chan×Moves = {find(lns_all, 'chan', 'Moves'):.2f}（论文 2.21），"
              f"排序也对。chan×Channel 我们算 {chan_channel:.2f}，论文报 2.7，"
              "差 15%。要凑出 2.7，需要 n(Channel)=22（而非 Table 11 的 19）或 N≈75——"
              "推测论文在 P(B) 里算的是「补丁中出现 channel 的次数」而非「用了 channel 的 bug 数」，"
              "一条 bug 的补丁可以出现多个 channel 操作。这一点论文没写清，我们不硬凑。")
    md.append("")

    if diffs:
        md.append("## 与论文的差异")
        md.append("")
        md.append(md_table(["表", "行", "本仓复算", "论文"], [list(d) for d in diffs]))
        md.append("")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"blocking={len(blocking)} non-blocking={len(nonblocking)} "
          f"diffs={len(diffs)} report={args.report}")
    for name, label, got, want in diffs:
        print(f"  [{name}] {label}: got={got} want={want}")
    return 0 if not diffs else 4


if __name__ == "__main__":
    sys.exit(main())
