#!/usr/bin/env python3
"""07_fig23.py — 画 Figure 2 / Figure 3，并与论文反解曲线对照。

输入：
    data/evolution_primitive_usage.csv   我们自己测的 6 应用 × 14 个季度的原语比例
    data/fig2_paper_raw.csv              从 PDF 反解出的 Fig 2 折线（extract_fig23.py）
    data/fig3_paper_raw.csv              同上，Fig 3

输出：
    report/figures/fig2_shared_memory.svg
    report/figures/fig3_message_passing.svg
    data/fig23_compare.csv               逐点对照 + 偏差统计

论文图里的颜色与应用的对应关系由图例色块位置确定；Docker 与 etcd 在图例里
同为纯黑，靠末点数值区分（etcd 收在 0.578/0.438，Docker 收在 0.718/0.298，
与 Table 4 的 57.0%/43.2% 和 72.3%/27.7% 对得上）。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

TICKS = ["15-02", "15-05", "15-08", "15-11", "16-02", "16-05", "16-08", "16-11",
         "17-02", "17-05", "17-08", "17-11", "18-02", "18-05"]

# app -> (显示名, 颜色, 线型)
STYLE = {
    "docker": ("Docker", "#1a202c", ""),
    "kubernetes": ("Kubernetes", "#e53e3e", ""),
    "etcd": ("etcd", "#2d3748", "6 4"),
    "cockroachdb": ("CockroachDB", "#2b6cb0", ""),
    "grpc-go": ("gRPC-Go", "#805ad5", ""),
    "boltdb": ("BoltDB", "#38a169", ""),
}
ORDER = ["docker", "kubernetes", "etcd", "cockroachdb", "grpc-go", "boltdb"]


def read_ours(path: Path) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["app"], []).append(float(r["sm_pct"]) / 100.0)
    for k in out:
        out[k] = out[k][: len(TICKS)]
    return out


def interp(pts: list[tuple[float, float]], x: float) -> float:
    """在 (i, v) 序列上线性插值。"""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def read_paper(raw: Path, panel: str, fig2: dict[str, list[float]] | None = None) -> dict[str, list[float]]:
    """把反解出来的曲线按颜色/末点映射到应用名。

    Fig 2 里两条黑线靠末点区分（etcd 收在 0.578、Docker 收在 0.718）。
    Fig 3 是 1 − Fig 2，末点大小关系反过来，所以用 Fig 2 的结果做锚：
    对每条黑线，看它更像 1−etcd 还是 1−Docker。
    """
    curves: list[tuple[tuple, list[float]]] = []
    with open(raw, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            col = tuple(float(x) for x in r["color"].strip("()").split(","))
            raw_pts = []
            for seg in r["points"].split(";"):
                i, v = seg.split(":")
                raw_pts.append((float(i), float(v)))
            # PDF 里共线的折点会被合并，点数可能少于 14；按索引线性插值回 14 个刻度
            pts = [interp(raw_pts, k) for k in range(len(TICKS))]
            curves.append((col, pts))

    blacks = [c for c in curves if c[0][0] < 0.05 and c[0][1] < 0.05 and c[0][2] < 0.05]
    out: dict[str, list[float]] = {}
    if len(blacks) >= 2:
        if fig2 is None:
            blacks.sort(key=lambda c: c[1][-1])  # 末点小的 = etcd
            out["etcd"] = blacks[0][1]
            out["docker"] = blacks[1][1]
        else:
            ref = {"etcd": 1 - mean(fig2["etcd"]), "docker": 1 - mean(fig2["docker"])}
            used = set()
            for app in ("etcd", "docker"):
                best = min((i for i in range(len(blacks)) if i not in used),
                           key=lambda i: abs(mean(blacks[i][1]) - ref[app]))
                out[app] = blacks[best][1]
                used.add(best)
    for col, pts in curves:
        r, g, b = col
        if r > 0.7 and g < 0.3:                  # 红
            out["kubernetes"] = pts
        elif b > 0.6 and r < 0.2:                # 蓝
            out["cockroachdb"] = pts
        elif r > 0.3 and b > 0.3 and g < 0.1:    # 紫
            out["grpc-go"] = pts
    return out


def render(series: dict[str, list[float]], paper: dict[str, list[float]],
           title: str, subtitle: str, ymax: float, out: Path) -> None:
    W, H = 780, 470
    L, R, T, B = 92, 726, 84, 356

    def sx(i: float) -> float:
        return L + (R - L) * i / (len(TICKS) - 1)

    def sy(v: float) -> float:
        return B - (B - T) * v / ymax

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="30" y="34" font-size="17" font-weight="bold" fill="#1a202c">{title}</text>',
         f'<text x="30" y="55" font-size="12" fill="#4a5568">{subtitle}</text>']

    # y 网格
    steps = 5 if ymax == 1.0 else 6
    for k in range(steps + 1):
        v = ymax * k / steps
        y = sy(v)
        s.append(f'<line x1="{L}" y1="{y:.1f}" x2="{R}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        s.append(f'<text x="{L-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#4a5568">'
                 f'{v:.1f}</text>')
    # x 刻度
    for i, t in enumerate(TICKS):
        x = sx(i)
        s.append(f'<line x1="{x:.1f}" y1="{T}" x2="{x:.1f}" y2="{B}" stroke="#edf2f7" stroke-width="1"/>')
        s.append(f'<text x="{x:.1f}" y="{B+18}" text-anchor="middle" font-size="10" '
                 f'fill="#4a5568">{t}</text>')
    s.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="#cbd5e0" stroke-width="1.2"/>')
    s.append(f'<line x1="{L}" y1="{T}" x2="{L}" y2="{B}" stroke="#cbd5e0" stroke-width="1.2"/>')
    s.append(f'<text x="{(L+R)/2:.0f}" y="{B+40}" text-anchor="middle" font-size="11" '
             'fill="#4a5568">2015-02 → 2018-05（每季度一个采样点，取该日期前最后一次提交）</text>')
    s.append(f'<text x="26" y="{(T+B)/2:.0f}" font-size="12" fill="#4a5568" '
             f'transform="rotate(-90 26 {(T+B)/2:.0f})" text-anchor="middle">Usage Proportion</text>')

    # 论文曲线（虚线、细）
    for app in ORDER:
        if app not in paper:
            continue
        _, color, _ = STYLE[app]
        pts = paper[app]
        d = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(pts[:len(TICKS)]))
        s.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.2" '
                 f'stroke-opacity="0.45" stroke-dasharray="3 3"/>')
    # 我们的曲线（实线、粗）
    for app in ORDER:
        if app not in series:
            continue
        name, color, dash = STYLE[app]
        pts = series[app]
        d = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(pts[:len(TICKS)]))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        s.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2.2"{dash_attr}/>')
        for i, v in enumerate(pts[:len(TICKS)]):
            s.append(f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="2.6" fill="{color}"/>')

    # 图例：放在坐标区下方，避免压到曲线（曲线都在上半区）
    names = [a for a in ORDER if a in series]
    per_row = 4
    for k, app in enumerate(names):
        name, color, dash = STYLE[app]
        row, col = divmod(k, per_row)
        xx = L + col * 158
        yy = B + 62 + row * 20
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        s.append(f'<line x1="{xx}" y1="{yy}" x2="{xx+24}" y2="{yy}" stroke="{color}" '
                 f'stroke-width="2.2"{dash_attr}/>')
        s.append(f'<text x="{xx+30}" y="{yy+4}" font-size="11" fill="#1a202c">{name}</text>')
    # 线型说明
    yy = B + 62 + 2 * 20
    s.append(f'<line x1="{L}" y1="{yy}" x2="{L+24}" y2="{yy}" stroke="#718096" stroke-width="2.2"/>')
    s.append(f'<text x="{L+30}" y="{yy+4}" font-size="11" fill="#1a202c">本文实测</text>')
    s.append(f'<line x1="{L+190}" y1="{yy}" x2="{L+214}" y2="{yy}" stroke="#718096" '
             'stroke-width="1.2" stroke-opacity="0.5" stroke-dasharray="3 3"/>')
    s.append(f'<text x="{L+220}" y="{yy+4}" font-size="11" fill="#1a202c">论文原图（矢量反解）</text>')
    s.append('</svg>')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(s), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", default="data/evolution_primitive_usage.csv")
    ap.add_argument("--fig2-raw", default="data/fig2_paper_raw.csv")
    ap.add_argument("--fig3-raw", default="data/fig3_paper_raw.csv")
    ap.add_argument("--figdir", default="report/figures")
    ap.add_argument("--cmp", default="data/fig23_compare.csv")
    args = ap.parse_args()

    ours = read_ours(Path(args.ours))
    p2 = read_paper(Path(args.fig2_raw), "2")
    p3 = read_paper(Path(args.fig3_raw), "3", fig2=p2)

    # Fig 3 = 1 - Fig 2（同一批原语的两个互补比例）；但我们用自己的 mp_pct 画，
    # 因此重新读一遍 mp 列
    mp: dict[str, list[float]] = {}
    with open(args.ours, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            mp.setdefault(r["app"], []).append(float(r["mp_pct"]) / 100.0)

    render(ours, p2, "Figure 2. Usages of shared-memory primitives over time",
           "proportion of shared-memory primitives over all primitives（本文 6 应用 × 14 季度）",
           1.0, Path(args.figdir) / "fig2_shared_memory.svg")
    render({k: v for k, v in mp.items()}, p3,
           "Figure 3. Usages of message-passing primitives over time",
           "proportion of message-passing primitives over all primitives（纵轴 0–0.6 便于分辨）",
           0.6, Path(args.figdir) / "fig3_message_passing.svg")

    # 逐点对照
    rows = []
    for app in ORDER:
        if app not in ours:
            continue
        for i in range(min(len(ours[app]), len(TICKS))):
            rows.append({
                "app": app, "tick": TICKS[i], "index": i,
                "ours_sm": round(ours[app][i], 3),
                "paper_sm": round(p2[app][i], 3) if app in p2 and i < len(p2[app]) else "",
                "ours_mp": round(mp[app][i], 3),
                "paper_mp": round(p3[app][i], 3) if app in p3 and i < len(p3[app]) else "",
            })
    out = Path(args.cmp)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{'app':12s} {'n':>3s} {'ours mean':>9s} {'range':>15s} {'paper mean':>10s} {'MAE':>6s} {'r':>6s}")
    for app in ORDER:
        if app not in ours:
            continue
        o = ours[app]
        mean = sum(o) / len(o)
        rng = f"{min(o):.3f}-{max(o):.3f}"
        if app in p2:
            pp = p2[app][: len(o)]
            mae = sum(abs(a - b) for a, b in zip(o, pp)) / len(pp)
            r = corr(o, pp)
            print(f"{app:12s} {len(o):3d} {mean:9.3f} {rng:>15s} {sum(pp)/len(pp):10.3f} "
                  f"{mae:6.3f} {r:6.2f}")
        else:
            print(f"{app:12s} {len(o):3d} {mean:9.3f} {rng:>15s} {'—':>10s} {'—':>6s} {'—':>6s}")
    print(f"[done] -> {args.figdir}/fig2_shared_memory.svg, fig3_message_passing.svg, {args.cmp}")
    return 0


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((x - mb) ** 2 for x in b) ** 0.5
    if va == 0 or vb == 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb)


if __name__ == "__main__":
    raise SystemExit(main())
