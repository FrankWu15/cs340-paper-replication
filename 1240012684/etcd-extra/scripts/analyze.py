#!/usr/bin/env python3
"""Generate statistics.csv, table_results.md and two SVG figures (no deps)."""
import csv, statistics, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "results", "summary.csv")
OUT = os.path.join(ROOT, "results")
FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)


def fnum(x):
    return None if x in ("NA", "") else float(x)


rows = list(csv.DictReader(open(CSV)))
groups = {}
for r in rows:
    groups.setdefault((r["bug"], r["mode"]), []).append(r)

stats = []
for (bug, mode), rs in sorted(groups.items()):
    n = len(rs)
    repro = sum(int(r["reproduced_deadlock"]) for r in rs)
    el = [fnum(r["elapsed_ms"]) for r in rs if fnum(r["elapsed_ms"]) is not None]
    mean = statistics.mean(el) if el else float("nan")
    sd = statistics.pstdev(el) if len(el) > 1 else 0.0
    stats.append((bug, mode, n, repro, mean, sd))

with open(os.path.join(OUT, "statistics.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["bug", "mode", "trials", "deadlocks_detected", "elapsed_ms_mean", "elapsed_ms_sd"])
    for s in stats:
        w.writerow(s)

with open(os.path.join(OUT, "table_results.md"), "w") as f:
    f.write("# etcd Reproduction Results\n\n")
    f.write("| Bug | Mode | Trials | Deadlocks detected | Elapsed ms (mean \u00b1 SD) |\n")
    f.write("|---|---|---:|---:|---|\n")
    for bug, mode, n, repro, mean, sd in stats:
        if mode == "buggy":
            f.write(f"| {bug} | {mode} | {n} | {repro}/{n} | n/a (deadlock) |\n")
        else:
            f.write(f"| {bug} | {mode} | {n} | {repro}/{n} | {mean:.2f} \u00b1 {sd:.2f} |\n")

# ---- Figure 1: detection rate (bar) -----------------------------------------
bugs = sorted({b for b, _ in groups})
rates = []
for b in bugs:
    rs = groups[(b, "buggy")]
    rates.append(100.0 * sum(int(r["reproduced_deadlock"]) for r in rs) / len(rs))

W, H = 560, 300
pad_l, pad_b = 60, 50
bw = 90
gap = (W - 2 * pad_l - len(bugs) * bw) / (len(bugs) + 1)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">']
svg.append(f'<rect width="{W}" height="{H}" fill="white"/>')
svg.append(f'<text x="{W/2}" y="22" font-size="14" text-anchor="middle" '
           f'font-family="sans-serif">Go runtime deadlock detector: reproducibility</text>')
svg.append(f'<line x1="{pad_l}" y1="{H-pad_b}" x2="{W-pad_l}" y2="{H-pad_b}" stroke="black"/>')
svg.append(f'<line x1="{pad_l}" y1="40" x2="{pad_l}" y2="{H-pad_b}" stroke="black"/>')
for i in range(0, 101, 20):
    y = H - pad_b - (H - pad_b - 40) * i / 100
    svg.append(f'<text x="{pad_l-6}" y="{y+4}" font-size="10" text-anchor="end">{i}</text>')
    svg.append(f'<line x1="{pad_l}" y1="{y}" x2="{W-pad_l}" y2="{y}" stroke="#ddd"/>')
for i, (b, r) in enumerate(zip(bugs, rates)):
    x = pad_l + gap + i * (bw + gap)
    y = H - pad_b - (H - pad_b - 40) * r / 100
    col = "#c0392b" if r >= 99 else "#e67e22"
    svg.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{H-pad_b-y}" fill="{col}"/>')
    svg.append(f'<text x="{x+bw/2}" y="{y-6}" font-size="12" text-anchor="middle">{r:.0f}%</text>')
    svg.append(f'<text x="{x+bw/2}" y="{H-pad_b+16}" font-size="11" text-anchor="middle">{b}</text>')
svg.append(f'<text x="14" y="{H/2}" font-size="11" transform="rotate(-90 14 {H/2})" '
           f'text-anchor="middle">Detection rate (%)</text>')
svg.append('</svg>')
open(os.path.join(FIG, "figE1_detection_rate.svg"), "w").write("\n".join(svg))

# ---- Figure 2: latency scatter for fixed runs ------------------------------
W, H = 560, 300
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">']
svg.append(f'<rect width="{W}" height="{H}" fill="white"/>')
svg.append(f'<text x="{W/2}" y="22" font-size="14" text-anchor="middle" '
           f'font-family="sans-serif">Fixed runs: exit latency (ms)</text>')
svg.append(f'<line x1="{pad_l}" y1="{H-pad_b}" x2="{W-pad_l}" y2="{H-pad_b}" stroke="black"/>')
svg.append(f'<line x1="{pad_l}" y1="40" x2="{pad_l}" y2="{H-pad_b}" stroke="black"/>')
maxv = max((s[4] for s in stats if s[2] and not s[4] != s[4]), default=1.0) or 1.0
for i, (b, r, n, rr, mean, sd) in enumerate(stats):
    if r != "fixed":
        continue
    x = pad_l + 80 + i * 120
    base = H - pad_b
    for _ in range(n):
        yy = base - (H - pad_b - 40) * min(mean, 5) / 5
        svg.append(f'<circle cx="{x}" cy="{yy:.1f}" r="3" fill="#2c7fb8"/>')
    svg.append(f'<text x="{x}" y="{H-pad_b+16}" font-size="11" text-anchor="middle">{b}</text>')
    svg.append(f'<text x="{x}" y="{base- (H-pad_b-40)*min(mean,5)/5 - 8}" font-size="10" '
               f'text-anchor="middle">mean {mean:.2f}</text>')
svg.append('</svg>')
open(os.path.join(FIG, "figE2_latency.svg"), "w").write("\n".join(svg))

print("analyzed", len(rows), "runs ->", os.path.join(OUT, "statistics.csv"),
      "+ 2 figures")
