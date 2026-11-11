#!/usr/bin/env python3
"""Build report/report.pdf from report/report.md and the measured statistics.

Requires reportlab and svglib (pip install reportlab svglib).  The Markdown
source is the editable master; the numbered tables and figures are embedded
verbatim, and the script refuses to build if the numbers in the report do not
match results/statistics.csv.

Usage: python3 scripts/make_report.py
"""
from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from svglib.svglib import svg2rlg

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "report" / "report.md"
PDF = ROOT / "report" / "report.pdf"
STATS = ROOT / "results" / "statistics.csv"
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 36 * mm

# ------------------------------------------------------------------ styles
ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold",
                            fontSize=17, leading=21, spaceAfter=10, alignment=0),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                         fontSize=13, leading=16, spaceBefore=14, spaceAfter=6,
                         textColor=colors.HexColor("#1a202c")),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                         fontSize=10.5, leading=13, spaceBefore=10, spaceAfter=4,
                         textColor=colors.HexColor("#2d3748")),
    "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica",
                           fontSize=9.2, leading=12.8, alignment=TA_JUSTIFY,
                           spaceAfter=5),
    "bullet": ParagraphStyle("bullet", parent=ss["BodyText"], fontName="Helvetica",
                             fontSize=9.2, leading=12.8, leftIndent=12,
                             bulletIndent=2, spaceAfter=3),
    "caption": ParagraphStyle("caption", parent=ss["BodyText"], fontName="Helvetica",
                              fontSize=8.6, leading=11.5, spaceBefore=3,
                              spaceAfter=8, textColor=colors.HexColor("#2d3748")),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.5, leading=9.4),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=7.5,
                            leading=9.4, textColor=colors.HexColor("#1a202c")),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8, leading=10),
}


def inline(text: str) -> str:
    # Stash code spans first: their contents may contain '*' (e.g. scripts/*)
    # which must not be mistaken for Markdown emphasis.
    text = text.replace("&nbsp;", " ")
    text = html.escape(text, quote=False)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00CODE{len(codes)-1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    for n, code in enumerate(codes):
        text = text.replace(f"\x00CODE{n}\x00",
                            f'<font face="Courier" size="8.5">{code}</font>')
    return text


def verify_numbers(md_text: str) -> None:
    """Refuse to build a report whose headline numbers disagree with the logs."""
    rows = {}
    with STATS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["mode"]] = r
    required = [
        f"{float(rows[m]['wall_clock_mean_ms']):.2f} +/- "
        f"{float(rows[m]['wall_clock_std_ms']):.2f}"
        for m in ("buggy", "move", "select", "live")
    ]
    required.append(
        f"{float(rows['buggy']['last_trace_mean_ms']):.2f} +/- "
        f"{float(rows['buggy']['last_trace_std_ms']):.2f}")
    missing = [x for x in required if x not in md_text]
    if missing:
        raise SystemExit("report/report.md disagrees with results/statistics.csv: "
                         + ", ".join(missing))
    print("[report] verified headline numbers against results/statistics.csv")


def split_row(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def make_table(lines):
    rows = [split_row(l) for l in lines if not is_separator(l)]
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]

    # Weight each column by its average text length so wide prose columns
    # (e.g. the deviation table's "Reason") get more room.
    weights = []
    for c in range(ncols):
        lens = [len(r[c]) for r in rows[1:]] or [10]
        weights.append(max(6, min(42, sum(lens) / len(lens))))
    total = sum(weights)
    widths = [CONTENT_W * w / total for w in weights]

    data = []
    for ri, row in enumerate(rows):
        style = S["cellb"] if ri == 0 else S["cell"]
        data.append([Paragraph(inline(c), style) for c in row])

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#fafbfc")]),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 7)]


def make_figure(path: Path):
    if not path.exists():
        print(f"[report] WARNING missing figure {path}", file=sys.stderr)
        return []
    drawing = svg2rlg(str(path))
    if drawing is None:
        return []
    w0, h0 = drawing.width, drawing.height
    scale = min(1.0, (CONTENT_W - 6) / w0)
    drawing.scale(scale, scale)
    drawing.width, drawing.height = w0 * scale, h0 * scale
    return [Spacer(1, 4), drawing, Spacer(1, 2)]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5e0"))
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, PAGE_W - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#4a5568"))
    canvas.drawString(18 * mm, 9.5 * mm, "CS340 Research Paper Replication - BoltDB#392")
    canvas.drawRightString(PAGE_W - 18 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    md_text = MD.read_text(encoding="utf-8")
    verify_numbers(md_text)
    lines = md_text.splitlines()
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            story.extend(make_table(block))
            continue

        if stripped.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
            if m:
                path = (MD.parent / m.group(2)).resolve()
                story.extend(make_figure(path))
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            story.append(Preformatted("\n".join(code), S["code"]))
            story.append(Spacer(1, 6))
            continue

        if stripped == "---":
            story.append(HRFlowable(width="100%", thickness=0.6,
                                   color=colors.HexColor("#cbd5e0"),
                                   spaceBefore=6, spaceAfter=8))
            i += 1
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(inline(stripped[2:]), S["title"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(inline(stripped[3:]), S["h1"]))
        elif stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), S["h2"]))
        elif stripped.startswith("- ") or re.match(r"^\d+\.\s", stripped):
            txt = re.sub(r"^(-|\d+\.)\s+", "", stripped)
            num = re.match(r"^(\d+)\.", stripped)
            story.append(Paragraph(inline(txt), S["bullet"],
                                   bulletText=(num.group(1) + "." if num else "\u2022")))
        elif stripped.startswith("**Figure") or stripped.startswith("**Table"):
            story.append(Paragraph(inline(stripped), S["caption"]))
        else:
            story.append(Paragraph(inline(stripped), S["body"]))
        i += 1

    doc = SimpleDocTemplate(
        str(PDF), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title="CS340 Reproduction: BoltDB#392",
        author="CS340 group", subject="Replication of ASPLOS'19 Go concurrency bug study")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"[report] wrote {PDF.relative_to(ROOT)} ({PDF.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
