#!/usr/bin/env python3
"""把 Markdown 表格源码按显示宽度对齐（中日韩字符占 2 列）。

用法: python mdtable.py FILE.md [FILE.md ...]

只重写由 `|` 开头的连续行块，不动其它内容。
"""
import re
import sys
import unicodedata

# 这些字符在终端里宽度为 0，但 east_asian_width 会算成 1
ZERO_WIDTH = {"\ufe0f", "\ufe0e", "\u200b", "\u200d"}


def dwidth(s: str) -> int:
    n = 0
    for ch in s:
        if ch in ZERO_WIDTH or unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def is_sep(cells):
    return all(re.fullmatch(r":?-{1,}:?", c.strip()) for c in cells if c.strip() != "")


def split_row(line: str):
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def fmt_block(rows, align_numeric=True):
    parsed = [split_row(r) for r in rows]
    ncol = max(len(r) for r in parsed)
    parsed = [r + [""] * (ncol - len(r)) for r in parsed]

    header, sep, body = parsed[0], parsed[1], parsed[2:]
    sepcells = sep
    right = [False] * ncol
    if align_numeric and body:
        num = re.compile(r"^[−+±-]?[\d,]+(?:\.\d+)?%?$")
        for i in range(ncol):
            vals = [r[i] for r in body if r[i] not in ("", "—", "-")]
            if vals and all(num.match(v) for v in vals):
                right[i] = True

    widths = []
    for i in range(ncol):
        cols = [header[i]] + [r[i] for r in body]
        widths.append(max(dwidth(c) for c in cols) if cols else 1)
        widths[-1] = max(widths[-1], 3)

    def pad(cell, i, header_row=False):
        gap = widths[i] - dwidth(cell)
        if right[i] and not header_row:
            return " " * gap + cell
        return cell + " " * gap

    out = []
    out.append("| " + " | ".join(pad(c, i, True) for i, c in enumerate(header)) + " |")
    line = "|"
    for i, c in enumerate(sepcells):
        w = widths[i] + 2
        left = c.strip().startswith(":")
        rightc = c.strip().endswith(":")
        if left and rightc:
            line += ":" + "-" * (w - 2) + ":|"
        elif rightc:
            line += "-" * (w - 1) + ":|"
        elif left:
            line += ":" + "-" * (w - 1) + "|"
        else:
            line += "-" * w + "|"
    out.append(line)
    for r in body:
        out.append("| " + " | ".join(pad(c, i) for i, c in enumerate(r)) + " |")
    return out


def process(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    out, i, changed, report = [], 0, 0, []
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            rows = lines[i:j]
            if len(rows) >= 2 and is_sep(split_row(rows[1])):
                new = fmt_block(rows)
                if new != rows:
                    changed += 1
                widest = max(dwidth(l) for l in new)
                report.append((i + 1, widest))
                out.extend(new)
            else:
                out.extend(rows)
            i = j
        else:
            out.append(lines[i])
            i += 1
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"{path}: 表 {len(report)} 张，改写 {changed} 张")
    for ln, w in report:
        flag = "  <-- 超过 92 列，可能折行" if w > 92 else ""
        print(f"    L{ln:<4} 宽 {w:>3}{flag}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        process(p)
