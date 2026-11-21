# -*- coding: utf-8 -*-
"""Builder for the reading-report DOCX files (English + Chinese)."""
import re
import os
import sys
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

LATIN = 'Times New Roman'
MONO = 'Consolas'
GRAY = RGBColor(0x55, 0x55, 0x55)
ACCENT = RGBColor(0x1F, 0x3B, 0x63)
RED = RGBColor(0xB0, 0x30, 0x20)
GREEN = RGBColor(0x1E, 0x6B, 0x35)
BLUE = RGBColor(0x1F, 0x3B, 0x63)


def set_run_font(run, latin=LATIN, ea='SimSun', size=None, bold=None, color=None, italic=None):
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.insert(0, rfonts)
    rfonts.set(qn('w:ascii'), latin)
    rfonts.set(qn('w:hAnsi'), latin)
    rfonts.set(qn('w:eastAsia'), ea)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color


def shade(par_or_cell, hexcolor):
    el = par_or_cell._element
    pr = el.get_or_add_pPr() if hasattr(el, 'get_or_add_pPr') else el.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hexcolor)
    pr.append(shd)


def border(paragraph, side='left', color='7F7F7F', size=12, space=6):
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn('w:pBdr'))
    if borders is None:
        borders = OxmlElement('w:pBdr')
        ppr.append(borders)
    el = OxmlElement('w:' + side)
    el.set(qn('w:val'), 'single')
    el.set(qn('w:sz'), str(size))
    el.set(qn('w:space'), str(space))
    el.set(qn('w:color'), color)
    borders.append(el)


class Ctx:
    def __init__(self, lang):
        self.zh = (lang == 'zh')
        self.body_ea = '宋体' if self.zh else 'SimSun'
        self.head_ea = '黑体' if self.zh else 'SimHei'
        self.indent = 21 if self.zh else 0
        self.bullet_lead = '：' if self.zh else ':'


def para(doc, ctx, text='', size=10.5, bold=False, italic=False, align=None,
         first_indent=None, space_before=0, space_after=6, line=1.35,
         color=None, ea=None, keep_next=False, left_indent=None, right_indent=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if first_indent is not None:
        pf.first_line_indent = Pt(first_indent)
    if left_indent is not None:
        pf.left_indent = Pt(left_indent)
    if right_indent is not None:
        pf.right_indent = Pt(right_indent)
    if align is not None:
        p.alignment = align
    if keep_next:
        pf.keep_with_next = True
    if text:
        r = p.add_run(text)
        set_run_font(r, ea=ea or ctx.body_ea, size=size, bold=bold, color=color, italic=italic)
    return p


def add_h(doc, ctx, text, level):
    sizes = {1: 15, 2: 12.5, 3: 11}
    p = doc.add_paragraph()
    p.style = doc.styles['Heading %d' % level]
    pf = p.paragraph_format
    pf.space_before = Pt(18 if level == 1 else 12)
    pf.space_after = Pt(8 if level == 1 else 5)
    pf.keep_with_next = True
    pf.line_spacing = 1.15
    r = p.add_run(text)
    set_run_font(r, ea=ctx.head_ea, size=sizes[level], bold=True, color=RGBColor(0, 0, 0))
    if level == 1:
        border(p, 'bottom', 'BFC6CF', 8, 3)
    return p


def add_code(doc, ctx, lines, caption=None):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    trpr = tbl.rows[0]._tr.get_or_add_trPr()
    trpr.append(OxmlElement('w:cantSplit'))
    cell = tbl.rows[0].cells[0]
    cell.width = Cm(15.2)
    shade(cell, 'F4F5F7')
    tcpr = cell._tc.get_or_add_tcPr()
    b = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        e = OxmlElement('w:' + side)
        e.set(qn('w:val'), 'single')
        e.set(qn('w:sz'), '4')
        e.set(qn('w:color'), 'C9CDD3')
        b.append(e)
    tcpr.append(b)
    p0 = cell.paragraphs[0]
    p0.paragraph_format.space_before = Pt(4)
    p0.paragraph_format.space_after = Pt(4)
    p0.paragraph_format.line_spacing = 1.0
    first = True
    for ln in lines:
        p = p0 if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.03
        p.paragraph_format.left_indent = Pt(2)
        m = re.match(r'^(\s*\d+)(\s*)([-+])?\s?(.*)$', ln)
        if m:
            num, gap, marker, rest = m.groups()
            r = p.add_run(num + gap)
            set_run_font(r, latin=MONO, ea=MONO, size=8.6, color=RGBColor(0x88, 0x88, 0x88))
            if marker:
                rm = p.add_run(marker + ' ')
                set_run_font(rm, latin=MONO, ea=MONO, size=8.6, bold=True,
                             color=RED if marker == '-' else GREEN)
            r2 = p.add_run(rest)
            set_run_font(r2, latin=MONO, ea=MONO, size=8.6)
        else:
            r = p.add_run(ln if ln else ' ')
            set_run_font(r, latin=MONO, ea=MONO, size=8.6)
    if caption:
        para(doc, ctx, caption, size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
             space_before=4, space_after=10, color=GRAY, italic=True)
    else:
        para(doc, ctx, '', size=3, space_after=6)


def add_table(doc, ctx, caption, header, rows, widths=None, size=8.6, align=None):
    ALIGN = {'l': WD_ALIGN_PARAGRAPH.LEFT, 'c': WD_ALIGN_PARAGRAPH.CENTER, 'r': WD_ALIGN_PARAGRAPH.RIGHT}
    if caption:
        para(doc, ctx, caption, size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
             space_before=8, space_after=3, color=GRAY, keep_next=True)
    ncols = len(header[0]) if header else len(rows[0])
    tbl = doc.add_table(rows=len(header) + len(rows), cols=ncols)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    tblPr.append(layout)
    mar = OxmlElement('w:tblCellMar')
    for side, val in (('top', '20'), ('left', '80'), ('bottom', '20'), ('right', '80')):
        e = OxmlElement('w:' + side)
        e.set(qn('w:w'), val)
        e.set(qn('w:type'), 'dxa')
        mar.append(e)
    tblPr.append(mar)
    total_w = 15.2
    if widths:
        s = sum(widths)
        widths = [w * total_w / s for w in widths]
    else:
        widths = [total_w / ncols] * ncols
    for ci, w in enumerate(widths):
        tbl.columns[ci].width = Cm(w)
    for row in tbl.rows:
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement('w:cantSplit'))
    for hi, hrow in enumerate(header):
        trpr = tbl.rows[hi]._tr.get_or_add_trPr()
        trpr.append(OxmlElement('w:tblHeader'))
        for ci, val in enumerate(hrow):
            cell = tbl.cell(hi, ci)
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run(val)
            set_run_font(r, ea=ctx.head_ea, size=size, bold=True)
            shade(cell, 'E9EDF2')
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri + len(header), ci)
            cell.text = ''
            p = cell.paragraphs[0]
            if align and ci < len(align):
                p.alignment = ALIGN.get(align[ci], WD_ALIGN_PARAGRAPH.CENTER)
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci == 0 else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(str(val))
            set_run_font(r, ea=ctx.body_ea, size=size)
    for ci, w in enumerate(widths):
        for row in tbl.rows:
            row.cells[ci].width = Cm(w)
    # keep report tables on a single page when they are small
    keep_together = len(tbl.rows) <= 10
    if keep_together:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True
    tail = para(doc, ctx, '', size=3, space_after=6)
    if not keep_together:
        tail.paragraph_format.keep_with_next = True
    return tbl


def add_kv(doc, ctx, rows, widths=(4.0, 11.2), size=9):
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    for ri, (k, v) in enumerate(rows):
        c0, c1 = tbl.rows[ri].cells
        c0.text = ''
        p = c0.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(k)
        set_run_font(r, ea=ctx.head_ea, size=size, bold=True)
        shade(c0, 'EDF0F4')
        c1.text = ''
        p = c1.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(v)
        set_run_font(r, ea=ctx.body_ea, size=size)
    for ri, row in enumerate(tbl.rows):
        row.cells[0].width = Cm(widths[0])
        row.cells[1].width = Cm(widths[1])
    para(doc, ctx, '', size=3, space_after=8)
    return tbl


def add_callout(doc, ctx, title, text, fill='EEF2F8', line='4A6FA5'):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(10)
    pf.right_indent = Pt(6)
    pf.space_before = Pt(8)
    pf.space_after = Pt(10)
    pf.line_spacing = 1.32
    shade(p, fill)
    border(p, 'left', line, 18, 6)
    if title:
        r1 = p.add_run(title + ('：' if ctx.zh else ': '))
        set_run_font(r1, ea=ctx.head_ea, size=10.2, bold=True, color=ACCENT)
    r2 = p.add_run(text)
    set_run_font(r2, ea=ctx.body_ea, size=10.2)
    return p


def add_quote(doc, ctx, text, source=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(16)
    pf.right_indent = Pt(10)
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    pf.line_spacing = 1.3
    border(p, 'left', 'A8894F', 12, 6)
    r = p.add_run(text)
    set_run_font(r, ea=ctx.body_ea, size=10, italic=True, color=RGBColor(0x33, 0x33, 0x33))
    if source:
        r2 = p.add_run('  ' + source)
        set_run_font(r2, ea=ctx.body_ea, size=9, color=GRAY)
    return p


def add_bullet(doc, ctx, text, numbered=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(26)
    pf.first_line_indent = Pt(-14)
    pf.space_before = Pt(2)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.3
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    mark = ('%s. ' % numbered) if numbered else ('• ' if not ctx.zh else '• ')
    r0 = p.add_run(mark)
    set_run_font(r0, ea=ctx.body_ea, size=10.5, bold=bool(numbered))
    sep = ctx.bullet_lead
    m = re.match(r'^([^%s]{2,48}%s)(.*)$' % (sep, sep), text) if (numbered is None and sep in text) else None
    if m:
        r1 = p.add_run(m.group(1))
        set_run_font(r1, ea=ctx.head_ea, size=10.5, bold=True)
        r2 = p.add_run(m.group(2))
        set_run_font(r2, ea=ctx.body_ea, size=10.5)
    else:
        r = p.add_run(text)
        set_run_font(r, ea=ctx.body_ea, size=10.5)


def build(blocks, out_path, lang):
    ctx = Ctx(lang)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.4)
    sec.bottom_margin = Cm(2.3)
    sec.left_margin = Cm(2.6)
    sec.right_margin = Cm(2.6)
    st = doc.styles['Normal']
    st.font.name = LATIN
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), ctx.body_ea)

    for blk in blocks:
        k = blk[0]
        if k == 'title':
            para(doc, ctx, blk[1], size=19, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT,
                 space_before=6, space_after=4, ea=ctx.head_ea, line=1.25)
        elif k == 'subtitle':
            para(doc, ctx, blk[1], size=10.5, italic=True, align=WD_ALIGN_PARAGRAPH.LEFT,
                 space_after=2, color=GRAY)
        elif k == 'meta':
            para(doc, ctx, blk[1], size=9, align=WD_ALIGN_PARAGRAPH.LEFT,
                 space_after=2, color=GRAY, line=1.2)
        elif k == 'h1':
            add_h(doc, ctx, blk[1], 1)
        elif k == 'h2':
            add_h(doc, ctx, blk[1], 2)
        elif k == 'h3':
            add_h(doc, ctx, blk[1], 3)
        elif k == 'p':
            para(doc, ctx, blk[1], size=10.5, first_indent=ctx.indent,
                 align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=6, line=1.38)
        elif k == 'lead':
            para(doc, ctx, blk[1], size=10.8, first_indent=ctx.indent,
                 align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=8, line=1.4)
        elif k == 'bullet':
            add_bullet(doc, ctx, blk[1])
        elif k == 'num':
            add_bullet(doc, ctx, blk[2], numbered=blk[1])
        elif k == 'callout':
            add_callout(doc, ctx, blk[1], blk[2])
        elif k == 'quote':
            add_quote(doc, ctx, blk[1], blk[2] if len(blk) > 2 else None)
        elif k == 'table':
            add_table(doc, ctx, blk[1], blk[2], blk[3],
                      widths=blk[4] if len(blk) > 4 else None,
                      align=blk[5] if len(blk) > 5 else None)
        elif k == 'kv':
            add_kv(doc, ctx, blk[2] if len(blk) > 2 else blk[1])
        elif k == 'code':
            add_code(doc, ctx, blk[2], blk[1])
        elif k == 'note':
            p = para(doc, ctx, blk[1], size=8.8, align=WD_ALIGN_PARAGRAPH.LEFT,
                     space_before=3, space_after=6, color=GRAY, line=1.25)
            p.paragraph_format.left_indent = Pt(10)
        elif k == 'pagebreak':
            doc.add_page_break()
        else:
            raise ValueError('unknown block %r' % (k,))

    footer = doc.sections[0].footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run()
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    run._element.addnext(fld)

    cp = doc.core_properties
    cp.title = blocks[0][1] if blocks and blocks[0][0] == 'title' else 'Reading report'
    cp.author = 'Reading notes'
    doc.save(out_path)
    return out_path
