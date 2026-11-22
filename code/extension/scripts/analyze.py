#!/usr/bin/env python3
"""ext-v2 analysis: trigger rate + Wilson CI, detection rate, false-negative risk.
Pure stdlib. Reads results/raw_runs.csv -> writes summary.csv, summary.md, figures/*.png
"""
import csv, os, math, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "results", "raw_runs.csv")
OUT_SUMM = os.path.join(HERE, "results", "summary.csv")
OUT_MD = os.path.join(HERE, "results", "summary.md")
FIGDIR = os.path.join(HERE, "results", "figures")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


rows = []
with open(RAW, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        r["gp"] = int(r["gp"])
        r["trig"] = int(r["trig"])
        r["race_flag"] = int(r["race_flag"])
        r["metric"] = int(r["metric"]) if r["metric"] else 0
        rows.append(r)

# ---------- D1: trigger rate per (case, gp, phase=plain) ----------
agg = defaultdict(lambda: [0, 0])  # (case,gp) -> [trig, n]
for r in rows:
    if r["phase"] == "plain":
        key = (r["case"], r["gp"])
        agg[key][1] += 1
        agg[key][0] += r["trig"]

cases = sorted({r["case"] for r in rows if r["phase"] == "plain"})
levels = sorted({r["gp"] for r in rows if r["phase"] == "plain"})

lines = ["# ext-v2 结果", "", "## D1 触发率（plain binary，触发率 + Wilson 95% CI）", "",
         "| case | class | " + " | ".join(f"gp={g}" for g in levels) + " |",
         "|" + "---|" * (len(levels) + 2)]

summ_rows = []
for c in cases:
    cls = ""
    for r in rows:
        if r["case"] == c:
            cls = r["class"]; break
    cells = []
    for g in levels:
        k, n = agg[(c, g)]
        p, lo, hi = wilson(k, n)
        cells.append(f"{k}/{n} ({p*100:.0f}% [{lo*100:.0f},{hi*100:.0f}])")
        summ_rows.append([c, cls, g, "plain", n, k, f"{p:.4f}", f"{lo:.4f}", f"{hi:.4f}"])
    lines.append(f"| {c} | {cls} | " + " | ".join(cells) + " |")
lines.append("")

# ---------- D1b: false-negative risk of "3 clean runs => not reproduced" ----------
lines += ["## D1b 若只跑 3 次、全干净就判「未复现」的假阴性概率", "",
          "对每档触发概率 p，误判概率 = (1-p)^3。", "",
          "| case | " + " | ".join(f"gp={g}" for g in levels) + " |",
          "|" + "---|" * (len(levels) + 1)]
for c in cases:
    cells = []
    for g in levels:
        k, n = agg[(c, g)]
        p = k / n if n else 0.0
        cells.append(f"{(1-p)**3*100:.1f}%")
    lines.append(f"| {c} | " + " | ".join(cells) + " |")
lines.append("")

# ---------- D2: detection rate per (case, gp, phase=race) ----------
ragg = defaultdict(lambda: [0, 0])
for r in rows:
    if r["phase"] == "race":
        key = (r["case"], r["gp"])
        ragg[key][1] += 1
        ragg[key][0] += r["race_flag"]

race_cases = sorted({r["case"] for r in rows if r["phase"] == "race"})
lines += ["## D2 竞态检出率（-race binary，'WARNING: DATA RACE' 出现率 + Wilson 95% CI）", "",
          "| case | " + " | ".join(f"gp={g}" for g in levels) + " |",
          "|" + "---|" * (len(levels) + 1)]
for c in race_cases:
    cells = []
    for g in levels:
        k, n = ragg[(c, g)]
        if n == 0:
            cells.append("—"); continue
        p, lo, hi = wilson(k, n)
        cells.append(f"{k}/{n} ({p*100:.0f}%)")
        summ_rows.append([c, "non-blocking", g, "race", n, k, f"{p:.4f}", f"{lo:.4f}", f"{hi:.4f}"])
    lines.append(f"| {c} | " + " | ".join(cells) + " |")
lines.append("")

# ---------- D1c: intensity (violation count among triggered runs) ----------
inten = defaultdict(list)
for r in rows:
    if r["phase"] == "plain" and r["trig"] == 1:
        inten[(r["case"], r["gp"])].append(r["metric"])
lines += ["## D1c 触发强度（仅统计已触发的运行，违规/不一致次数均值）", "",
          "这一维才是并行度影响最大的地方：'触发与否'在 gp≥2 就饱和，但'触发得多猛'随核数放大一个量级。", "",
          "| case | " + " | ".join(f"gp={g}" for g in levels) + " |",
          "|" + "---|" * (len(levels) + 1)]
for c in cases:
    cells = []
    for g in levels:
        v = inten.get((c, g), [])
        cells.append(f"{sum(v)/len(v):.1f}" if v else "—")
    lines.append(f"| {c} | " + " | ".join(cells) + " |")
lines.append("")
fix = defaultdict(lambda: [0, 0])
for r in rows:
    if r["phase"] == "fixed":
        fix[r["case"]][1] += 1
        fix[r["case"]][0] += r["trig"]
lines += ["## 对照组：fixed 版触发率（应全 0）", ""]
for c in sorted(fix):
    k, n = fix[c]
    lines.append(f"- `{c}`：{k}/{n} 触发")

os.makedirs(FIGDIR, exist_ok=True)
with open(OUT_SUMM, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "class", "gp", "phase", "n", "triggers", "rate", "ci_lo", "ci_hi"])
    w.writerows(summ_rows)

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# ---------- figures ----------
try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

if HAVE_PIL:
    W, H = 1600, 620
    BG = (255, 255, 255); FG = (32, 32, 32); GRID = (225, 225, 225)
    COLORS = [(200, 40, 40), (40, 90, 200), (30, 140, 70), (150, 90, 20), (120, 40, 150)]

    def font(sz):
        for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
            if os.path.exists(p):
                try: return ImageFont.truetype(p, sz)
                except Exception: pass
        return ImageFont.load_default()

    def panel(draw, x0, y0, w, h, title, series, ymax=100, ylabel=""):
        draw.text((x0, y0 - 34), title, fill=FG, font=font(20))
        # axes
        draw.line([(x0, y0), (x0, y0 + h)], fill=FG, width=2)
        draw.line([(x0, y0 + h), (x0 + w, y0 + h)], fill=FG, width=2)
        for t in range(0, 5):
            yy = y0 + h - h * t / 4
            draw.line([(x0, yy), (x0 + w, yy)], fill=GRID, width=1)
            draw.text((x0 - 46, yy - 8), f"{ymax*t//4}", fill=FG, font=font(14))
        if ylabel:
            draw.text((x0 - 44, y0 - 22), ylabel, fill=FG, font=font(14))
        n = len(levels)
        for si, (label, vals) in enumerate(series):
            pts = []
            for i, v in enumerate(vals):
                cxp = x0 + (w * (i + 0.5) / n)
                cyp = y0 + h - h * (v / ymax)
                pts.append((cxp, cyp))
            col = COLORS[si % len(COLORS)]
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i + 1]], fill=col, width=3)
            for (cxp, cyp) in pts:
                draw.ellipse([cxp - 5, cyp - 5, cxp + 5, cyp + 5], fill=col)
        # legend top-left inside panel (avoids end-of-line label collisions)
        for si, (label, vals) in enumerate(series):
            col = COLORS[si % len(COLORS)]
            lx, ly = x0 + 10, y0 + 10 + si * 20
            draw.line([(lx, ly + 6), (lx + 22, ly + 6)], fill=col, width=3)
            draw.text((lx + 28, ly - 1), label, fill=col, font=font(13))
        for i, g in enumerate(levels):
            cxp = x0 + (w * (i + 0.5) / n)
            draw.text((cxp - 18, y0 + h + 8), f"gp={g}", fill=FG, font=font(14))
            draw.text((cxp - 14, y0 + h + 26), f"{g}核" if g == 1 else "", fill=(120,120,120), font=font(11))

    img = Image.new("RGB", (1960, 640), BG); d = ImageDraw.Draw(img)
    d.text((40, 22), "Ext-v2: scheduler parallelism vs trigger rate, trigger intensity, and race-detector hit rate", fill=FG, font=font(23))

    # panel 1: trigger rate (%) -- non-blocking prob cases
    prob_series = []
    for c in cases:
        cls = next(r["class"] for r in rows if r["case"] == c)
        if cls != "non-blocking":
            continue
        vals = [100.0 * agg[(c, g)][0] / agg[(c, g)][1] if agg[(c, g)][1] else 0 for g in levels]
        prob_series.append((c.replace("-", " "), vals))
    panel(d, 100, 120, 520, 400, "Trigger rate (%)", prob_series, ymax=100)

    # panel 2: intensity (violations among triggered runs) -- only cases with a real counter
    inten_series = []
    ymax_i = 200
    for c in ("cockroachdb-17112", "moby-28682"):
        vals = []
        for g in levels:
            v = inten.get((c, g), [])
            vals.append(sum(v) / len(v) if v else 0)
        inten_series.append((c.replace("-", " "), vals))
    panel(d, 760, 120, 520, 400, "Trigger intensity (violations/run)", inten_series, ymax=ymax_i)

    # panel 3: race-detector hit rate (%)
    race_series = []
    for c in race_cases:
        vals = [100.0 * ragg[(c, g)][0] / ragg[(c, g)][1] if ragg[(c, g)][1] else 0 for g in levels]
        race_series.append((c.replace("-", " "), vals))
    panel(d, 1420, 120, 520, 400, "Race-detector hit rate (%)", race_series, ymax=100)

    img.save(os.path.join(FIGDIR, "ext_v2_curves.png"))
    print("figure saved:", os.path.join(FIGDIR, "ext_v2_curves.png"))

print("wrote", OUT_SUMM)
print("wrote", OUT_MD)
print(open(OUT_MD, encoding="utf-8").read())
