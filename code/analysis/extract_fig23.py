#!/usr/bin/env python3
"""extract_fig23.py — 从论文 PDF 里反解 Figure 2 / Figure 3 的曲线数值。

论文没有给 Fig 2/3 的数据表，只有图。要判断"我们的曲线和论文像不像"，
只能把图里的折线还原成数字。做法与 Fig 4 那次一致（get_drawings 取矢量路径）：

    1. 用 y 轴刻度标签（0, 0.2, … 1）与 x 轴刻度标签（15−02 … 18−05）
       做最小二乘标定，建立"像素 → 数据值"的线性映射；
    2. 取图框内 items ≥ 10 的描边路径，逐点映射成 (季度序号, 比例)；
    3. 颜色 → 应用由图例色块的位置确定。

注意两处不可解：
    * Docker 与 etcd 在图例里都是纯黑 (0,0,0)，两条黑线无法仅凭颜色区分；
    * BoltDB 的绿线在 Fig 2 里只画出一段（x 158→214），其余区间被别的线盖住，
      pymupdf 仍然只返回可见段。
因此本脚本输出的是"可辨识曲线"的近似值，精度约 ±0.02（约 1.5 px）。

用法：
    python extract_fig23.py --pdf ../../go-study.pdf --panel 2 --out fig2_paper.csv
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import pymupdf

# 两个面板的横向范围（由图例色块与折线 rect 实测）
PANELS = {
    "2": {"x0": 88.0, "x1": 220.0, "y0": 80.0, "y1": 158.0, "lab_x": 70.0, "lab_xmax": 82.0},
    "3": {"x0": 255.0, "x1": 386.0, "y0": 80.0, "y1": 152.0, "lab_x": 239.0, "lab_xmax": 252.0},
}

YLAB = re.compile(r"^(0|1|0\.\d)$")
XLAB = re.compile(r"^1[5-8][−-]\d\d$")


def fit(pairs):
    """最小二乘 y = a + b*x，返回 (a, b, rms)。"""
    n = len(pairs)
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sxx = sum(p[0] * p[0] for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    den = n * sxx - sx * sx
    b = (n * sxy - sx * sy) / den
    a = (sy - b * sx) / n
    rms = (sum((a + b * p[0] - p[1]) ** 2 for p in pairs) / n) ** 0.5
    return a, b, rms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, default=5, help="1-based 页码")
    ap.add_argument("--panel", choices=["2", "3"], required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    page = doc[args.page - 1]
    box = PANELS[args.panel]

    # ---- 标定：y 轴用刻度标签中心，x 轴用刻度标签中心
    y_pairs, x_pairs = [], []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                t = span["text"].strip()
                x0, y0, x1, y1 = span["bbox"]
                cy = (y0 + y1) / 2
                if (YLAB.match(t) and box["lab_x"] <= x0 <= box["lab_xmax"]
                        and box["y0"] <= cy <= box["y1"]):
                    y_pairs.append((float(t), cy))
                if XLAB.match(t):
                    cx = (x0 + x1) / 2
                    if box["x0"] - 10 <= cx <= box["x1"] + 10:
                        x_pairs.append((cx, t))

    y_pairs.sort(key=lambda p: p[1], reverse=True)   # 值大在上（y 小）
    if len(y_pairs) < 5 or len(x_pairs) < 10:
        print(f"[x] 标定点不足: y={len(y_pairs)} x={len(x_pairs)}")
        return 1
    a0, b0, rms0 = fit([(v, y) for v, y in y_pairs])
    # y = a0 + b0*v  →  v = (y - a0)/b0
    print(f"[calib] y轴: y = {a0:.2f} + {b0:.2f}*v  rms={rms0:.2f}px  n={len(y_pairs)}")
    print("[calib] v=1 像素 y=%.2f, v=0 像素 y=%.2f" % (a0 + b0, a0))

    x_pairs.sort()
    idx = list(range(len(x_pairs)))
    ax_, bx_, rmsx = fit(list(zip(idx, [p[0] for p in x_pairs])))
    print(f"[calib] x轴: x = {ax_:.2f} + {bx_:.2f}*i  rms={rmsx:.2f}px  n={len(x_pairs)}")

    def to_v(y: float) -> float:
        return (y - a0) / b0

    def to_i(x: float) -> float:
        return (x - ax_) / bx_

    rows = []
    for d in page.get_drawings():
        r = d["rect"]
        if not (box["x0"] <= r.x0 and r.x1 <= box["x1"] and box["y0"] <= r.y0 and r.y1 <= box["y1"]):
            continue
        if len(d["items"]) < 10 or d["type"] != "s":
            continue
        col = tuple(round(c, 2) for c in d["color"]) if d.get("color") else None
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if not pts:
                    pts.append(p1)
                pts.append(p2)
        if len(pts) < 8:
            continue
        vals = [(round(to_i(p.x), 2), round(to_v(p.y), 3)) for p in pts]
        rows.append({"panel": args.panel, "color": col, "n": len(vals),
                     "points": ";".join(f"{i:.1f}:{v:.3f}" for i, v in vals)})
        print(f"  color={col} n={len(vals)} v_first={vals[0][1]:.3f} v_last={vals[-1][1]:.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["panel", "color", "n", "points"])
        w.writeheader()
        w.writerows(rows)
    print(f"[done] {len(rows)} 条曲线 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
