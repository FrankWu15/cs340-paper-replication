# -*- coding: utf-8 -*-
"""Build the Chinese translation DOCX of the Go concurrency bug paper."""
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from content_part1 import BLOCKS as B1
from content_part2 import BLOCKS as B2
from content_part3 import BLOCKS as B3
from content_part4 import BLOCKS as B4
from content_part5 import BLOCKS as B5

BLOCKS = B1 + B2 + B3 + B4 + B5

BODY_EA = '宋体'
HEAD_EA = '黑体'
LATIN = 'Times New Roman'
MONO = 'Consolas'

GRAY = RGBColor(0x59, 0x59, 0x59)
RED = RGBColor(0xB0, 0x30, 0x20)
GREEN = RGBColor(0x1E, 0x6B, 0x35)
BLUE = RGBColor(0x1F, 0x3B, 0x63)


def set_run_font(run, latin=LATIN, ea=BODY_EA, size=None, bold=None, color=None):
    run.font.name = latin
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    rfonts.set(qn('w:ascii'), latin)
    rfonts.set(qn('w:hAnsi'), latin)
    rfonts.set(qn('w:eastAsia'), ea)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def shade(paragraph_or_cell, hexcolor):
    el = paragraph_or_cell._element
    pr = el.get_or_add_pPr() if hasattr(el, 'get_or_add_pPr') else el.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hexcolor)
    pr.append(shd)


def left_border(paragraph, color='7F7F7F', size=12):
    ppr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement('w:pBdr')
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single')
    left.set(qn('w:sz'), str(size))
    left.set(qn('w:space'), '6')
    left.set(qn('w:color'), color)
    borders.append(left)
    ppr.append(borders)


def para(doc, text='', size=10.5, bold=False, italic=False, align=None,
         first_indent=None, space_before=0, space_after=6, line=1.35,
         color=None, latin=LATIN, ea=BODY_EA, keep_next=False, left_indent=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if first_indent is not None:
        pf.first_line_indent = Pt(first_indent)
    if left_indent is not None:
        pf.left_indent = Pt(left_indent)
    if align is not None:
        p.alignment = align
    if keep_next:
        pf.keep_with_next = True
    if text:
        r = p.add_run(text)
        set_run_font(r, latin=latin, ea=ea, size=size, bold=bold, color=color)
        r.font.italic = italic
    return p


def add_heading(doc, text, level):
    sizes = {1: 15, 2: 12.5, 3: 11}
    p = doc.add_paragraph()
    p.style = doc.styles['Heading %d' % level]
    pf = p.paragraph_format
    pf.space_before = Pt(16 if level == 1 else 11)
    pf.space_after = Pt(7 if level == 1 else 5)
    pf.keep_with_next = True
    pf.line_spacing = 1.2
    r = p.add_run(text)
    set_run_font(r, ea=HEAD_EA, size=sizes[level], bold=True, color=RGBColor(0, 0, 0))
    return p


def add_code(doc, lines, caption=None):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.rows[0].cells[0]
    shade(cell, 'F4F5F7')
    cell.width = Cm(15.6)
    # thin border
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        b = OxmlElement('w:' + side)
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '4')
        b.set(qn('w:color'), 'C9CDD3')
        borders.append(b)
    tcpr.append(borders)
    # keep the whole listing on one page
    trpr = tbl.rows[0]._tr.get_or_add_trPr()
    cant = OxmlElement('w:cantSplit')
    trpr.append(cant)
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
        # sub-figure label line, e.g. "（a）goroutine 1"
        if re.match(r'^（[a-z]）', ln):
            p.paragraph_format.space_before = Pt(6)
            r = p.add_run(ln)
            set_run_font(r, ea=HEAD_EA, size=9, bold=True, color=RGBColor(0x44, 0x44, 0x44))
            continue
        # split optional line number and diff marker
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
        cap = para(doc, caption, size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                   space_before=4, space_after=10, color=GRAY)
    else:
        para(doc, '', size=4, space_after=6)


def add_table(doc, caption, header, rows, widths=None, first_col_left=True, size=8.5,
              header_rows=1):
    cap = para(doc, caption, size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
               space_before=7, space_after=3, color=GRAY, keep_next=True)
    ncols = len(header[0]) if header else len(rows[0])
    tbl = doc.add_table(rows=len(header) + len(rows), cols=ncols)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    # fixed layout
    tblPr = tbl._tbl.tblPr
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    tblPr.append(layout)
    # compact cell margins
    mar = OxmlElement('w:tblCellMar')
    for side, val in (('top', '8'), ('left', '70'), ('bottom', '8'), ('right', '70')):
        el = OxmlElement('w:' + side)
        el.set(qn('w:w'), val)
        el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tblPr.append(mar)
    total_w = 15.4
    if widths:
        s = sum(widths)
        widths = [w * total_w / s for w in widths]
    else:
        widths = [total_w / ncols] * ncols
    for ci, w in enumerate(widths):
        tbl.columns[ci].width = Cm(w)
    # header rows repeat on page breaks, rows never split
    for row in tbl.rows:
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement('w:cantSplit'))
    for hi, hrow in enumerate(header):
        trpr = tbl.rows[hi]._tr.get_or_add_trPr()
        th = OxmlElement('w:tblHeader')
        trpr.append(th)
    # header
    for hi, hrow in enumerate(header):
        for ci, val in enumerate(hrow):
            cell = tbl.cell(hi, ci)
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(val)
            set_run_font(r, ea=HEAD_EA, size=size, bold=True)
            shade(cell, 'EDEFF2')
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri + len(header), ci)
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if (ci == 0 and first_col_left) else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(str(val))
            set_run_font(r, ea=BODY_EA, size=size)
    if widths:
        for ci, w in enumerate(widths):
            for row in tbl.rows:
                row.cells[ci].width = Cm(w)
    # keep the last rows and the note together, but allow the table to break
    # between rows (the header row repeats) so pages are not left half empty
    if len(tbl.rows) <= 10:
        for row in tbl.rows[-2:]:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True
    tail = para(doc, '', size=3, space_after=6)
    tail.paragraph_format.keep_with_next = True
    return tbl


def add_callout(doc, label, text, color_hex='EEF2F8', border='4A6FA5'):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(10)
    pf.right_indent = Pt(6)
    pf.space_before = Pt(6)
    pf.space_after = Pt(8)
    pf.line_spacing = 1.3
    shade(p, color_hex)
    left_border(p, border, 18)
    r1 = p.add_run(label + '：')
    set_run_font(r1, ea=HEAD_EA, size=10.2, bold=True, color=BLUE)
    r2 = p.add_run(text)
    set_run_font(r2, ea=BODY_EA, size=10.2)
    return p


def add_bullet(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Pt(24)
    pf.first_line_indent = Pt(-12)
    pf.space_before = Pt(2)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.3
    r0 = p.add_run('• ')
    set_run_font(r0, ea=BODY_EA, size=10.5)
    # bold lead-in up to first "：" if present
    m = re.match(r'^([^：]{2,40}：)(.*)$', text)
    if m:
        r1 = p.add_run(m.group(1))
        set_run_font(r1, ea=HEAD_EA, size=10.5, bold=True)
        r2 = p.add_run(m.group(2))
        set_run_font(r2, ea=BODY_EA, size=10.5)
    else:
        r = p.add_run(text)
        set_run_font(r, ea=BODY_EA, size=10.5)


def build(out_path):
    doc = Document()

    # page setup A4
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.4)
    sec.bottom_margin = Cm(2.3)
    sec.left_margin = Cm(2.6)
    sec.right_margin = Cm(2.6)

    # base style
    st = doc.styles['Normal']
    st.font.name = LATIN
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), BODY_EA)

    for blocks in [BLOCKS]:
        for blk in blocks:
            kind = blk[0]
            if kind == 'title':
                para(doc, blk[1], size=20, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_before=10, space_after=6, ea=HEAD_EA, line=1.25)
            elif kind == 'subtitle':
                para(doc, blk[1], size=11, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_after=10, color=GRAY)
            elif kind == 'meta':
                para(doc, blk[1], size=9.2, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_after=3, color=GRAY, line=1.2)
            elif kind == 'authors':
                para(doc, blk[1], size=11, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_before=6, space_after=2)
            elif kind == 'affil':
                para(doc, blk[1], size=9.2, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_after=2, color=GRAY, line=1.2)
            elif kind == 'h1':
                add_heading(doc, blk[1], 1)
            elif kind == 'h2':
                add_heading(doc, blk[1], 2)
            elif kind == 'h3':
                add_heading(doc, blk[1], 3)
            elif kind == 'p':
                para(doc, blk[1], size=10.5, first_indent=21, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                     space_after=6, line=1.38)
            elif kind == 'pl':
                para(doc, blk[1], size=10.5, first_indent=21, align=WD_ALIGN_PARAGRAPH.LEFT,
                     space_after=6, line=1.38)
            elif kind == 'pr':
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.space_before = Pt(2)
                pf.space_after = Pt(6)
                pf.line_spacing = 1.38
                pf.first_line_indent = Pt(21)
                align_left = len(blk) > 3 and blk[3] == 'left'
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if align_left else WD_ALIGN_PARAGRAPH.JUSTIFY
                r1 = p.add_run(blk[1])
                set_run_font(r1, ea=HEAD_EA, size=10.5, bold=True)
                r2 = p.add_run('：' + blk[2])
                set_run_font(r2, ea=BODY_EA, size=10.5)
            elif kind == 'kw':
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(10)
                p.paragraph_format.line_spacing = 1.3
                r1 = p.add_run('关键词：')
                set_run_font(r1, ea=HEAD_EA, size=9.8, bold=True)
                r2 = p.add_run(blk[1])
                set_run_font(r2, ea=BODY_EA, size=9.8)
            elif kind == 'obs':
                add_callout(doc, blk[1], blk[2], 'EEF2F8', '4A6FA5')
            elif kind == 'impl':
                add_callout(doc, blk[1], blk[2], 'F5F1E8', 'A8894F')
            elif kind == 'code':
                add_code(doc, blk[2], blk[1] if len(blk) > 1 else None)
            elif kind == 'table':
                add_table(doc, blk[1], blk[2], blk[3], widths=blk[4] if len(blk) > 4 else None)
            elif kind == 'bullet':
                add_bullet(doc, blk[1])
            elif kind == 'caption':
                para(doc, blk[1], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_before=4, space_after=10, color=GRAY)
            elif kind == 'note':
                p = para(doc, blk[1], size=9, align=WD_ALIGN_PARAGRAPH.LEFT,
                         space_before=4, space_after=8, color=GRAY, line=1.25)
                p.paragraph_format.left_indent = Pt(12)
            elif kind == 'figplaceholder':
                # blk[1] = placeholder note, blk[2] = caption
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.left_indent = Pt(30)
                pf.right_indent = Pt(30)
                pf.space_before = Pt(8)
                pf.space_after = Pt(3)
                pf.line_spacing = 1.1
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                shade(p, 'F6F7F9')
                r = p.add_run(blk[1])
                set_run_font(r, ea=BODY_EA, size=9, color=GRAY, latin=LATIN)
                r.font.italic = True
                para(doc, blk[2], size=9, align=WD_ALIGN_PARAGRAPH.CENTER,
                     space_before=2, space_after=10, color=GRAY)
            elif kind == 'refhead':
                add_heading(doc, blk[1], 1)
            elif kind == 'ref':
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.left_indent = Pt(26)
                pf.first_line_indent = Pt(-26)
                pf.space_before = Pt(0)
                pf.space_after = Pt(2)
                pf.line_spacing = 1.15
                r = p.add_run(blk[1])
                set_run_font(r, ea=BODY_EA, size=8.3)
            elif kind == 'pagebreak':
                doc.add_page_break()
            else:
                raise ValueError('unknown block kind: %r' % (kind,))

    # footer page numbers
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run()
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), 'PAGE')
    run._element.addnext(fld)
    r = fp.add_run('')
    set_run_font(r, size=9, color=GRAY)

    # document properties
    cp = doc.core_properties
    cp.title = '理解 Go 语言真实世界中的并发缺陷（中文译稿）'
    cp.subject = 'Understanding Real-World Concurrency Bugs in Go 之中文翻译'
    cp.author = 'Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang（原著）；中文译稿'
    cp.keywords = 'Go; 并发缺陷; 阻塞型缺陷; 非阻塞型缺陷; 消息传递; 共享内存'
    cp.comments = 'ASPLOS ’19 论文中文译稿，图表编号与原文一致。'

    doc.save(out_path)
    print('saved', out_path)


if __name__ == '__main__':
    build('理解Go语言真实世界中的并发缺陷（中文译稿）.docx')
