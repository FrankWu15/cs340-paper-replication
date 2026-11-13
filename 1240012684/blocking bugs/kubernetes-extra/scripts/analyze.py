#!/usr/bin/env python3
"""Compute mean +/- SD and a summary figure from results/summary.csv.

Standard library only, so it runs on a clean Linux machine.
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

GROUPS = [("double-rlock", "buggy"), ("double-rlock", "fixed"),
          ("miss-unlock", "buggy"), ("miss-unlock", "fixed")]
LABEL = {
    ("double-rlock", "buggy"): "double RLock / buggy",
    ("double-rlock", "fixed"): "double RLock / fixed",
    ("miss-unlock", "buggy"): "miss unlock / buggy",
    ("miss-unlock", "fixed"): "miss unlock / fixed",
}
COLOR = {"buggy": "#c0392b", "fixed": "#1e7a46"}


def main():
    with (RES / "summary.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("summary.csv is empty - run scripts/run_experiments.sh first")

    stats = []
    with (RES / "statistics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bug", "mode", "n", "deadlock_detected", "detection_rate",
                    "timeout_rate", "wall_clock_mean_ms", "wall_clock_std_ms"])
        for bug, mode in GROUPS:
            r = [x for x in rows if x["bug"] == bug and x["mode"] == mode]
            wall = [float(x["wall_clock_ms"]) for x in r]
            det = [int(x["deadlock_reported"]) for x in r]
            to = [int(x["timed_out"]) for x in r]
            mean = statistics.mean(wall)
            sd = statistics.stdev(wall) if len(wall) > 1 else 0.0
            w.writerow([bug, mode, len(r), sum(det), f"{sum(det)/len(det):.4f}",
                        f"{sum(to)/len(to):.4f}", f"{mean:.3f}", f"{sd:.3f}"])
            stats.append((bug, mode, len(r), sum(det), mean, sd))

    lines = ["| Bug | Mode | n | Deadlock reported | Wall clock (ms), mean +/- SD |",
             "|---|---|---:|---:|---:|"]
    for bug, mode, n, det, mean, sd in stats:
        lines.append(f"| {bug} | {mode} | {n} | {det}/{n} ({100*det/n:.0f}%) | "
                     f"{mean:.2f} +/- {sd:.2f} |")
    (RES / "table_results.md").write_text(
        "**Table K1.** Minimal Kubernetes blocking-bug reproductions, "
        f"{stats[0][2]} independent trials per group. SD is the sample standard "
        "deviation (n-1). Wall clock measured outside the process with "
        "`date +%s%N`.\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    # Simple SVG bar chart of detection rate.
    w, h = 720, 360
    left, top, ph, pw = 90, 80, 210, 590
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
         f'width="{w}" height="{h}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
         f'<text x="30" y="32" font-size="16" font-weight="bold" fill="#1a202c">'
         f'Figure K1. Deadlock detection rate (Kubernetes minimal reproductions)</text>',
         f'<text x="30" y="52" font-size="12" fill="#4a5568">'
         f'Go built-in detector, {stats[0][2]} trials per group</text>']
    for k in range(6):
        y = top + ph - ph * k / 5
        s.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+pw}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        s.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="#4a5568">{20*k:g}</text>')
    s.append(f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#4a5568"/>')
    s.append(f'<text x="20" y="{top-14}" font-size="12" fill="#1a202c">Trials detected (%)</text>')
    bw = pw / 4 * 0.45
    for i, (bug, mode, n, det, mean, sd) in enumerate(stats):
        cx = left + pw * (i + 0.5) / 4
        pct = 100 * det / n
        bh = ph * pct / 100
        y = top + ph - bh
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                 f'fill="{COLOR[mode]}" rx="3"/>')
        s.append(f'<text x="{cx:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="12" '
                 f'font-weight="bold" fill="#1a202c">{pct:.0f}%</text>')
        for j, part in enumerate(LABEL[(bug, mode)].split(" / ")):
            s.append(f'<text x="{cx:.1f}" y="{top+ph+22+j*15:.1f}" text-anchor="middle" '
                     f'font-size="11" fill="#1a202c">{part}</text>')
    s.append('</svg>')
    (RES / "figK1_detection_rate.svg").write_text("\n".join(s) + "\n", encoding="utf-8")

    print("wrote results/statistics.csv, table_results.md, figK1_detection_rate.svg")
    for bug, mode, n, det, mean, sd in stats:
        print(f"  {bug:13s} {mode:6s} n={n:2d} detected={det:2d}/{n:2d} "
              f"wall={mean:.2f}+/-{sd:.2f} ms")


if __name__ == "__main__":
    main()
