#!/usr/bin/env python3
"""Generate a dependency-free SVG bar chart from results/raw/statistics.csv.

Shows race_detected rate for each (toolchain, mode, build) group, making the
non-blocking verdict visually obvious:
  buggy + race  -> full bar (bug reproduced on BOTH Go versions)
  everything else -> empty (fix works / silent non-blocking plain run)
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APPS = ["kubernetes-capabilities-race", "etcd-consistent-index-race"]

# (key, label, color) — color encodes expected outcome
GROUPS = [
    ("go126|buggy|race",  "Go 1.26  buggy  -race", "#c0392b"),
    ("go126|fixed|race",  "Go 1.26  fixed  -race", "#27ae60"),
    ("go126|buggy|plain", "Go 1.26  buggy  plain", "#7f8c8d"),
    ("go126|fixed|plain", "Go 1.26  fixed  plain", "#7f8c8d"),
    ("go18|buggy|race",   "Go 1.8   buggy  -race", "#c0392b"),
    ("go18|fixed|race",   "Go 1.8   fixed  -race", "#27ae60"),
]


def load(app):
    path = os.path.join(ROOT, app, "results", "raw", "statistics.csv")
    counts = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = f"{row['toolchain']}|{row['mode']}|{row['build']}"
            n, r = counts.get(key, (0, 0))
            counts[key] = (n + 1, r + int(row["race_detected"]))
    return counts


def chart(app):
    counts = load(app)
    W, H = 760, 70 + len(GROUPS) * 46
    left, bar_x, bar_w = 250, 260, 420
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="Helvetica,Arial,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="24" y="32" font-size="17" font-weight="bold" fill="#2c3e50">'
        f'Data-race detection — {app}</text>',
        f'<text x="24" y="51" font-size="12" fill="#607d8b">'
        f'"WARNING: DATA RACE" reported / 20 runs (go build -race)</text>',
    ]
    for i, (key, label, color) in enumerate(GROUPS):
        y = 70 + i * 46
        n, r = counts.get(key, (0, 0))
        frac = r / n if n else 0
        parts.append(
            f'<text x="{left-12}" y="{y+16}" text-anchor="end" font-size="12.5" '
            f'fill="#34495e">{label}</text>')
        parts.append(
            f'<rect x="{bar_x}" y="{y+3}" width="{bar_w}" height="20" rx="3" '
            f'fill="#ecf0f1" stroke="#bdc3c7" stroke-width="0.5"/>')
        if frac > 0:
            parts.append(
                f'<rect x="{bar_x}" y="{y+3}" width="{bar_w*frac:.1f}" height="20" '
                f'rx="3" fill="{color}"/>')
        parts.append(
            f'<text x="{bar_x+bar_w+10}" y="{y+18}" font-size="12.5" '
            f'font-weight="bold" fill="#2c3e50">{r}/{n}</text>')
    # legend / annotation
    ay = 70 + len(GROUPS) * 46 + 6
    parts.append(
        f'<text x="24" y="{ay}" font-size="11.5" fill="#7f8c8d">'
        f'Red = race present (bug reproduced)   Green = fix removes race   '
        f'Grey = plain build (no detector; silent, NO deadlock)</text>')
    parts.append('</svg>')
    svg = "\n".join(parts)
    out = os.path.join(ROOT, app, "results", "figures", "race_detection_summary.svg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out}")
    for key, label, _ in GROUPS:
        n, r = counts.get(key, (0, 0))
        print(f"  {label:26s} {r}/{n}")


if __name__ == "__main__":
    for a in APPS:
        p = os.path.join(ROOT, a, "results", "raw", "statistics.csv")
        if not os.path.exists(p):
            print(f"SKIP {a}: no statistics.csv yet", file=sys.stderr)
            continue
        print(f"=== {a} ===")
        chart(a)
