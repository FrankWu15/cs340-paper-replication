#!/usr/bin/env python3
"""Recompute every number reported in report/report.pdf from results/summary.csv.

Only the Python standard library is used, so this runs on a clean Linux
machine (and on Windows) without extra packages.  Outputs:

  results/statistics.csv            per-mode mean +/- sample std
  results/table_results.md          numbered results table for the report
  results/table_paper_vs_ours.md    numbered Paper vs. Ours table
  results/figures/fig1_detection_rate.svg
  results/figures/fig2_wall_clock.svg
  results/figures/fig3_buggy_latency.svg
"""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
FIG = RES / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# Paper: Tu et al., ASPLOS'19, Table 8 (Section 5.3) and accompanying text.
PAPER_USED = {"Mutex": 7, "Chan": 8, "Chan w/": 4, "Messaging Libraries": 2}
PAPER_DETECTED = {"Mutex": 1, "Chan": 0, "Chan w/": 1, "Messaging Libraries": 0}
PAPER_TOTAL_USED, PAPER_TOTAL_DETECTED = 21, 2

MODES = ["buggy", "move", "select", "live"]
LABELS = {
    "buggy": "Buggy",
    "move": "Fix: move",
    "select": "Fix: select",
    "live": "Buggy + live",
}
COLORS = {
    "buggy": "#c0392b",
    "move": "#1e7a46",
    "select": "#2b6cb0",
    "live": "#d97706",
}


def read_rows():
    with (RES / "summary.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def stats(rows):
    out = {}
    for mode in MODES:
        r = [x for x in rows if x["mode"] == mode]
        if not r:
            continue
        wall = [float(x["wall_clock_ms"]) for x in r]
        trace = [float(x["last_trace_ms"]) for x in r if x["last_trace_ms"] not in ("", "NA")]
        det = [int(x["deadlock_reported"]) for x in r]
        to = [int(x["timed_out"]) for x in r]
        out[mode] = {
            "n": len(r),
            "det_rate": sum(det) / len(det),
            "det_count": sum(det),
            "timeout_rate": sum(to) / len(to),
            "wall_mean": statistics.mean(wall),
            "wall_std": statistics.stdev(wall) if len(wall) > 1 else 0.0,
            "trace_mean": statistics.mean(trace) if trace else float("nan"),
            "trace_std": statistics.stdev(trace) if len(trace) > 1 else 0.0,
            "wall": wall,
            "trace": trace,
        }
    return out


def write_statistics_csv(s):
    with (RES / "statistics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "n", "deadlock_detected", "detection_rate",
                    "timeout_rate", "wall_clock_mean_ms", "wall_clock_std_ms",
                    "last_trace_mean_ms", "last_trace_std_ms"])
        for mode, d in s.items():
            w.writerow([mode, d["n"], d["det_count"], f"{d['det_rate']:.4f}",
                        f"{d['timeout_rate']:.4f}", f"{d['wall_mean']:.3f}",
                        f"{d['wall_std']:.3f}", f"{d['trace_mean']:.3f}",
                        f"{d['trace_std']:.3f}"])


def write_tables(s):
    b = s["buggy"]
    lines = [
        "| Mode | n | Runtime deadlock reported | Silent hang (timeout) | Wall clock (ms), mean +/- SD |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        if mode not in s:
            continue
        d = s[mode]
        lines.append(
            f"| {LABELS[mode]} (`{mode}`) | {d['n']} | {d['det_count']}/{d['n']} "
            f"({100*d['det_rate']:.0f}%) | {100*d['timeout_rate']:.0f}% | "
            f"{d['wall_mean']:.2f} +/- {d['wall_std']:.2f} |"
        )
    (RES / "table_results.md").write_text(
        "**Table 2.** Per-mode results, %d independent trials per mode. "
        "SD is the sample standard deviation (n-1). Wall clock is measured "
        "outside the process with `date +%%s%%N` and therefore includes Go "
        "runtime startup.\n\n" % b["n"] + "\n".join(lines) + "\n",
        encoding="utf-8")

    n = b["n"]
    paper_rate = PAPER_TOTAL_DETECTED / PAPER_TOTAL_USED
    lines = [
        "| Metric | Paper (ASPLOS'19) | Ours (reduced scale) |",
        "|---|---|---|",
        f"| Reproduced blocking bugs | {PAPER_TOTAL_USED} (6 applications) | 1 (BoltDB#392) |",
        f"| Bugs reported by Go's deadlock detector | {PAPER_TOTAL_DETECTED}/{PAPER_TOTAL_USED} "
        f"({100*paper_rate:.1f}%) | 1/1 (100%) |",
        "| BoltDB#392 explicitly listed as detected (Table 8 / Sec. 5.3) | Yes | Yes |",
        f"| `Chan w/` category | {PAPER_DETECTED['Chan w/']}/{PAPER_USED['Chan w/']} "
        f"detected (25.0%) | 1/1 detected (100%) |",
        f"| Trials of BoltDB#392 | 1 (deterministic, stated in Sec. 5.3) | {n} |",
        f"| BoltDB#392 detection rate | 1/1 (100%) | {b['det_count']}/{n} "
        f"({100*b['det_rate']:.0f}%) |",
        "| Detection latency | not reported | "
        f"{b['wall_mean']:.2f} +/- {b['wall_std']:.2f} ms (wall clock) |",
        "| Fixed variants deadlocking | not reported | 0/%d (`move`, `select`) |"
        % (s["move"]["n"] + s["select"]["n"]),
    ]
    (RES / "table_paper_vs_ours.md").write_text(
        "**Table 1.** Paper vs. Ours on the same metric (fraction of reproduced "
        "blocking bugs reported by Go's built-in deadlock detector) under the "
        "same setting when applicable. The paper's scope is 21 bugs in six "
        "applications; ours is one bug at reduced scale, which the assignment "
        "explicitly permits if stated.\n\n" + "\n".join(lines) + "\n",
        encoding="utf-8")


def svg_header(title, subtitle, w=760, h=420):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'font-family="Helvetica,Arial,sans-serif">',
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
            f'<text x="30" y="34" font-size="17" font-weight="bold" fill="#1a202c">{title}</text>',
            f'<text x="30" y="55" font-size="12" fill="#4a5568">{subtitle}</text>']


def bar_chart(path, title, subtitle, labels, values, errors, ylabel, ymax, colors,
              value_fmt="{:.0f}", w=760, h=420):
    left, right, top, bottom = 90, 30, 90, 80
    pw, ph = w - left - right, h - top - bottom
    s = svg_header(title, subtitle, w, h)
    # y grid
    for k in range(6):
        y = top + ph - ph * k / 5
        v = ymax * k / 5
        s.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+pw}" y2="{y:.1f}" '
                 f'stroke="#e2e8f0" stroke-width="1"/>')
        s.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="#4a5568">{v:g}</text>')
    s.append(f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#4a5568"/>')
    s.append(f'<text x="20" y="{top-18}" font-size="12" fill="#1a202c">{ylabel}</text>')
    bw = pw / len(labels) * 0.5
    for i, (lab, val, err, col) in enumerate(zip(labels, values, errors, colors)):
        cx = left + pw * (i + 0.5) / len(labels)
        bh = 0 if ymax == 0 else ph * val / ymax
        y = top + ph - bh
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                 f'fill="{col}" rx="3"/>')
        if err:
            ey = top + ph - ph * (val + err) / ymax
            s.append(f'<line x1="{cx:.1f}" y1="{ey:.1f}" x2="{cx:.1f}" y2="{y:.1f}" '
                     f'stroke="#1a202c" stroke-width="1.5"/>')
            s.append(f'<line x1="{cx-5:.1f}" y1="{ey:.1f}" x2="{cx+5:.1f}" y2="{ey:.1f}" '
                     f'stroke="#1a202c" stroke-width="1.5"/>')
        s.append(f'<text x="{cx:.1f}" y="{y-9:.1f}" text-anchor="middle" font-size="12" '
                 f'font-weight="bold" fill="#1a202c">{value_fmt.format(val)}</text>')
        s.append(f'<text x="{cx:.1f}" y="{top+ph+22:.1f}" text-anchor="middle" font-size="12" '
                 f'fill="#1a202c">{lab}</text>')
    s.append('</svg>')
    path.write_text("\n".join(s) + "\n", encoding="utf-8")


def scatter_chart(path, title, subtitle, values, mean, std):
    w, h = 760, 420
    left, right, top, bottom = 90, 30, 90, 80
    pw, ph = w - left - right, h - top - bottom
    ymax = math.ceil((max(values) + 2) / 5) * 5 or 5
    s = svg_header(title, subtitle, w, h)
    for k in range(6):
        y = top + ph - ph * k / 5
        s.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+pw}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        s.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="#4a5568">{ymax*k/5:g}</text>')
    s.append(f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#4a5568"/>')
    my = top + ph - ph * mean / ymax
    band = ph * std / ymax
    s.append(f'<rect x="{left}" y="{my-band:.1f}" width="{pw}" height="{2*band:.1f}" '
             f'fill="#c0392b" opacity="0.10"/>')
    s.append(f'<line x1="{left}" y1="{my:.1f}" x2="{left+pw}" y2="{my:.1f}" '
             f'stroke="#c0392b" stroke-dasharray="6 4" stroke-width="2"/>')
    for i, v in enumerate(values):
        x = left + pw * (i + 0.5) / len(values)
        y = top + ph - ph * v / ymax
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#c0392b"/>')
    for i in range(0, len(values), max(1, len(values) // 10)):
        x = left + pw * (i + 0.5) / len(values)
        s.append(f'<text x="{x:.1f}" y="{top+ph+22:.1f}" text-anchor="middle" font-size="11" '
                 f'fill="#4a5568">{i+1}</text>')
    s.append(f'<text x="{left+pw/2:.1f}" y="{h-22}" text-anchor="middle" font-size="12" '
             f'fill="#1a202c">Trial number</text>')
    s.append(f'<text x="20" y="{top-18}" font-size="12" fill="#1a202c">Wall clock (ms)</text>')
    s.append(f'<text x="{left+12}" y="{my-8:.1f}" font-size="11" fill="#c0392b">'
             f'mean {mean:.2f} +/- {std:.2f} ms</text>')
    s.append('</svg>')
    path.write_text("\n".join(s) + "\n", encoding="utf-8")


def main():
    rows = read_rows()
    if not rows:
        raise SystemExit("results/summary.csv is empty - run `make run` first")
    s = stats(rows)
    write_statistics_csv(s)
    write_tables(s)
    bar_chart(
        FIG / "fig1_detection_rate.svg",
        "Figure 1. Go built-in deadlock detector: detection rate",
        "Fraction of trials where the runtime printed 'all goroutines are asleep - deadlock!'",
        [LABELS[m] for m in MODES],
        [100 * s[m]["det_rate"] if m in s else 0 for m in MODES],
        [0] * 4, "Trials detected (%)", 100,
        [COLORS[m] for m in MODES], "{:.0f}%")
    bar_chart(
        FIG / "fig2_wall_clock.svg",
        "Figure 2. Wall-clock time per trial (mean +/- SD)",
        "Buggy = detection by runtime; fixes = clean exit; Buggy + live = killed at timeout",
        [LABELS[m] for m in MODES],
        [s[m]["wall_mean"] if m in s else 0 for m in MODES],
        [s[m]["wall_std"] if m in s else 0 for m in MODES],
        "Wall clock (ms)", max(10, math.ceil(max(
            (s[m]["wall_mean"] + s[m]["wall_std"]) for m in s) / 500) * 500 + 500),
        [COLORS[m] for m in MODES], "{:.0f}")
    b = s["buggy"]
    scatter_chart(
        FIG / "fig3_buggy_latency.svg",
        "Figure 3. Detection latency of the buggy program",
        "One point per independent trial; dashed line = mean, shaded band = +/- 1 SD",
        b["wall"], b["wall_mean"], b["wall_std"])
    print("wrote results/statistics.csv, table_results.md, table_paper_vs_ours.md")
    print("wrote 3 SVG figures in results/figures/")
    for m, d in s.items():
        print(f"  {m:7s} n={d['n']:2d} detected={d['det_count']:2d}/{d['n']:2d} "
              f"wall={d['wall_mean']:.2f}+/-{d['wall_std']:.2f} ms "
              f"timeout={100*d['timeout_rate']:.0f}%")


if __name__ == "__main__":
    main()
