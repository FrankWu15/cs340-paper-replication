import re, zlib, sys, io

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

data = open(r'go-study.pdf', 'rb').read()

def parse_objects(data):
    objs = {}
    for m in re.finditer(rb'(?<![0-9])(\d+)\s+(\d+)\s+obj\b', data):
        num = int(m.group(1))
        start = m.end()
        e = data.find(b'endobj', start)
        if e == -1:
            e = len(data)
        objs[num] = data[start:e]
    return objs

objs = parse_objects(data)

def get_stream(body):
    i = body.find(b'stream')
    if i == -1:
        return None
    j = i + 6
    if body[j:j+2] == b'\r\n':
        j += 2
    elif body[j:j+1] in (b'\n', b'\r'):
        j += 1
    k = body.rfind(b'endstream')
    if k == -1:
        return None
    return body[j:k]

def inflate(body):
    s = get_stream(body)
    if s is None:
        return None
    try:
        return zlib.decompress(s)
    except Exception:
        try:
            return zlib.decompressobj().decompress(s)
        except Exception:
            return None

allobj = dict(objs)
for num0, body in list(objs.items()):
    if b'/ObjStm' in body:
        dec = inflate(body)
        n = int(re.search(rb'/N\s+(\d+)', body).group(1))
        first = int(re.search(rb'/First\s+(\d+)', body).group(1))
        hdr = dec[:first].split()
        pairs = [(int(hdr[i]), int(hdr[i+1])) for i in range(0, 2*n, 2)]
        for idx, (onum, off) in enumerate(pairs):
            end = pairs[idx+1][1] + first if idx+1 < len(pairs) else len(dec)
            allobj.setdefault(onum, dec[first+off:end])

ref_re = re.compile(rb'(\d+)\s+0\s+R')

def obj_of(num):
    return allobj.get(num, b'')

def resolve(tok):
    if tok is None:
        return b''
    m = ref_re.fullmatch(tok.strip())
    if m:
        return allobj.get(int(m.group(1)), b'')
    return tok

def dict_get(body, key):
    m = re.search(rb'/' + key + rb'(?![\w])\s*(<<|\/[^\s/<>\[\]()]+|\[[^\]]*\]|\d+\s+0\s+R|[\d.+-]+)', body)
    if not m:
        return None
    if m.group(1) == b'<<':
        i = m.end() - 2
        depth = 0
        for j in range(i, len(body)):
            if body[j:j+2] == b'<<':
                depth += 1
            elif body[j:j+2] == b'>>':
                depth -= 1
                if depth == 0:
                    return body[i:j+2]
        return None
    return m.group(1)

def tofloat(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

# ---------- page tree ----------
catalog = None
for num0, b in allobj.items():
    if b'/Type' in b and b'/Catalog' in b:
        catalog = b
        break
root_pages = int(re.search(rb'/Pages\s+(\d+)', catalog).group(1))
pages = []
def walk(node):
    b = obj_of(node)
    if re.search(rb'/Type\s*/Page\b', b):
        pages.append(node)
        return
    kids = dict_get(b, b'Kids')
    if kids:
        for m in re.finditer(rb'(\d+)\s+0\s+R', kids):
            walk(int(m.group(1)))
walk(root_pages)

# ---------- fonts ----------
def parse_tounicode(stream):
    cmap = {}
    if not stream:
        return cmap
    txt = stream.decode('latin-1')
    for m in re.finditer(r'beginbfchar(.*?)endbfchar', txt, re.S):
        for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', m.group(1)):
            code = int(src, 16)
            cmap[code] = ''.join(chr(int(dst[i:i+4], 16)) for i in range(0, len(dst), 4))
    for m in re.finditer(r'beginbfrange(.*?)endbfrange', txt, re.S):
        body = m.group(1)
        for mm in re.finditer(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]+>)', body):
            lo, hi, dst = int(mm.group(1), 16), int(mm.group(2), 16), mm.group(3)
            if dst.startswith('['):
                items = re.findall(r'<([0-9A-Fa-f]+)>', dst)
                for k, it in enumerate(items):
                    cmap[lo+k] = ''.join(chr(int(it[i:i+4], 16)) for i in range(0, len(it), 4))
            else:
                base = int(dst[1:-1], 16)
                for k in range(hi - lo + 1):
                    cmap[lo+k] = chr(base + k)
    return cmap

GLYPHS = {
 'space':' ','exclam':'!','quotedbl':'"','numbersign':'#','dollar':'$','percent':'%',
 'ampersand':'&','quoteright':'\u2019','quotesingle':"'",'parenleft':'(','parenright':')',
 'asterisk':'*','plus':'+','comma':',','hyphen':'-','period':'.','slash':'/','colon':':',
 'semicolon':';','less':'<','equal':'=','greater':'>','question':'?','at':'@','bracketleft':'[',
 'backslash':'\\','bracketright':']','asciicircum':'^','underscore':'_','quoteleft':'\u2018',
 'grave':'`','braceleft':'{','bar':'|','braceright':'}','asciitilde':'~','endash':'\u2013',
 'emdash':'\u2014','quotedblleft':'\u201c','quotedblright':'\u201d','bullet':'\u2022',
 'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7',
 'eight':'8','nine':'9','fi':'\ufb01','fl':'\ufb02','ff':'ff','ffi':'\ufb03','ffl':'\ufb04',
 'quotedblbase':'\u201e','quotesinglbase':'\u201a','ellipsis':'\u2026','dagger':'\u2020',
 'daggerdbl':'\u2021','section':'\u00a7','paragraph':'\u00b6','germandbls':'\u00df',
 'guillemotleft':'\u00ab','guillemotright':'\u00bb','degree':'\u00b0','periodcentered':'\u00b7',
 'minus':'\u2212',
}
for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
    GLYPHS[c] = c

def glyph_to_uni(name):
    if name in GLYPHS:
        return GLYPHS[name]
    if re.fullmatch(r'uni[0-9A-Fa-f]{4}', name):
        return chr(int(name[3:], 16))
    if re.fullmatch(r'[A-Za-z]', name):
        return name
    return ''

def parse_font(num):
    b = obj_of(num)
    f = {'widths': {}, 'cmap': {}, 'uni': {}, 'name': b'?'}
    f['name'] = dict_get(b, b'BaseFont') or b'?'
    first = int(tofloat(dict_get(b, b'FirstChar') or b'0'))
    w = dict_get(b, b'Widths')
    if w:
        vals = [float(x) for x in re.findall(rb'[-\d.]+', w)]
        for i, v in enumerate(vals):
            f['widths'][first + i] = v
    tu = dict_get(b, b'ToUnicode')
    if tu and ref_re.fullmatch(tu.strip()):
        st = obj_of(int(ref_re.fullmatch(tu.strip()).group(1)))
        f['cmap'] = parse_tounicode(inflate(st))
    enc = dict_get(b, b'Encoding')
    enc = resolve(enc)
    if enc and b'Differences' in enc:
        diffs = enc.split(b'Differences', 1)[1]
        cur = 0
        for m in re.finditer(rb'(\d+)|/([A-Za-z0-9_.]+)', diffs):
            if m.group(1):
                cur = int(m.group(1))
            else:
                f['uni'][cur] = glyph_to_uni(m.group(2).decode('latin-1'))
                cur += 1
    return f

fonts_cache = {}
def font_for(num):
    if num not in fonts_cache:
        fonts_cache[num] = parse_font(num)
    return fonts_cache[num]

# ---------- content tokenizer ----------
def tokenize(s):
    i, n = 0, len(s)
    toks = []
    while i < n:
        c = s[i:i+1]
        if c in b' \t\r\n\x0c\x00':
            i += 1
            continue
        if c == b'%':
            while i < n and s[i:i+1] not in b'\r\n':
                i += 1
            continue
        if c == b'(':
            depth = 1
            i += 1
            buf = bytearray()
            while i < n and depth:
                ch = s[i:i+1]
                if ch == b'\\':
                    nxt = s[i+1:i+2]
                    esc = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f',
                           b'(': b'(', b')': b')', b'\\': b'\\'}
                    if nxt in esc:
                        buf += esc[nxt]
                        i += 2
                    elif nxt.isdigit():
                        digits = b''
                        j = i + 1
                        while j < n and len(digits) < 3 and s[j:j+1].isdigit():
                            digits += s[j:j+1]
                            j += 1
                        buf.append(int(digits, 8) & 0xFF)
                        i = j
                    elif nxt in (b'\n', b'\r'):
                        i += 2
                    else:
                        buf += nxt
                        i += 2
                elif ch == b'(':
                    depth += 1
                    buf += ch
                    i += 1
                elif ch == b')':
                    depth -= 1
                    if depth:
                        buf += ch
                    i += 1
                else:
                    buf += ch
                    i += 1
            toks.append(('str', bytes(buf)))
            continue
        if c == b'<':
            if s[i:i+2] == b'<<':
                toks.append(('op', b'<<'))
                i += 2
                continue
            j = s.find(b'>', i)
            h = re.sub(rb'\s', b'', s[i+1:j])
            if len(h) % 2:
                h += b'0'
            toks.append(('str', bytes.fromhex(h.decode('latin-1'))))
            i = j + 1
            continue
        if c in b'[]':
            toks.append(('op', c))
            i += 1
            continue
        if c == b'/':
            j = i + 1
            while j < n and s[j:j+1] not in b' \t\r\n\x0c/[]<>(){}%':
                j += 1
            toks.append(('name', s[i:j]))
            i = j
            continue
        if c in b'+-.0123456789':
            m = re.match(rb'[+-]?(\d+\.?\d*|\.\d+)', s[i:])
            if m and m.group(0) not in (b'', b'+', b'-', b'.'):
                toks.append(('num', float(m.group(0))))
                i += len(m.group(0))
                continue
        j = i
        while j < n and s[j:j+1] not in b' \t\r\n\x0c/[]<>(){}%':
            j += 1
        if j == i:
            j = i + 1
        toks.append(('op', s[i:j]))
        i = j
    return toks

def mat_mul(a, b):
    return (a[0]*b[0] + a[1]*b[2], a[0]*b[1] + a[1]*b[3],
            a[2]*b[0] + a[3]*b[2], a[2]*b[1] + a[3]*b[3],
            a[4]*b[0] + a[5]*b[2] + b[4], a[4]*b[1] + a[5]*b[3] + b[5])

def apply(m, x, y):
    return (m[0]*x + m[2]*y + m[4], m[1]*x + m[3]*y + m[5])

def emit(b, tm, ctm, font, fsize):
    out = []
    m = mat_mul(tm, ctm)
    scale = (m[0]**2 + m[1]**2) ** 0.5
    x, y = apply(m, 0, 0)
    for ch in b:
        code = ch
        u = None
        if font:
            if code in font['cmap']:
                u = font['cmap'][code]
            elif code in font['uni']:
                u = font['uni'][code]
        if u is None or u == '':
            u = chr(code) if 32 <= code < 127 else ''
        w = font['widths'].get(code, 500) if font else 500
        adv = w / 1000.0 * fsize * scale
        out.append((x, y, fsize * scale, u, adv))
        x += adv
    return out

def advance(b, tm, font, fsize):
    total = 0.0
    for ch in b:
        w = font['widths'].get(ch, 500) if font else 500
        total += w / 1000.0 * fsize
    return mat_mul((1, 0, 0, 1, total, 0), tm)

# ---------- extract page glyphs ----------
pages_glyphs = []
for pnum in pages:
    pbody = obj_of(pnum)
    res = resolve(dict_get(pbody, b'Resources'))
    fontdict = {}
    fd = dict_get(res, b'Font')
    fd = resolve(fd)
    if fd:
        for m in re.finditer(rb'/([A-Za-z0-9_.+-]+)\s+(\d+)\s+0\s+R', fd):
            fontdict[m.group(1)] = int(m.group(2))
    contents = dict_get(pbody, b'Contents')
    refs = [int(x) for x in re.findall(rb'(\d+)\s+0\s+R', contents or b'')]
    stream = b''
    for r in refs:
        d = inflate(obj_of(r))
        if d:
            stream += d + b'\n'
    toks = tokenize(stream)

    glyphs = []
    ctm = (1, 0, 0, 1, 0, 0)
    tm = (1, 0, 0, 1, 0, 0)
    tlm = tm
    font = None
    fsize = 10.0
    leading = 0.0
    stack = []
    operands = []
    for typ, val in toks:
        if typ != 'op':
            operands.append((typ, val))
            continue
        op = val
        if op in (b'[', b']'):
            operands.append(('op', op))
            continue
        if op == b'q':
            stack.append(ctm)
        elif op == b'Q':
            if stack:
                ctm = stack.pop()
        elif op == b'cm' and len(operands) >= 6:
            ctm = mat_mul(tuple(v for _, v in operands[-6:]), ctm)
        elif op == b'BT':
            tm = (1, 0, 0, 1, 0, 0)
            tlm = tm
        elif op == b'Tf' and len(operands) >= 2:
            nm = operands[-2][1]
            fsize = operands[-1][1]
            font = font_for(fontdict[nm[1:]]) if nm[1:] in fontdict else None
        elif op == b'Td' and len(operands) >= 2:
            tlm = mat_mul((1, 0, 0, 1, operands[-2][1], operands[-1][1]), tlm)
            tm = tlm
        elif op == b'TD' and len(operands) >= 2:
            leading = -operands[-1][1]
            tlm = mat_mul((1, 0, 0, 1, operands[-2][1], operands[-1][1]), tlm)
            tm = tlm
        elif op == b'Tm' and len(operands) >= 6:
            tm = tuple(v for _, v in operands[-6:])
            tlm = tm
        elif op == b'T*':
            tlm = mat_mul((1, 0, 0, 1, 0, -leading), tlm)
            tm = tlm
        elif op in (b'Tj', b"'", b'"'):
            if op in (b"'", b'"'):
                tlm = mat_mul((1, 0, 0, 1, 0, -leading), tlm)
                tm = tlm
            if operands and operands[-1][0] == 'str':
                sbytes = operands[-1][1]
                glyphs.extend(emit(sbytes, tm, ctm, font, fsize))
                tm = advance(sbytes, tm, font, fsize)
        elif op == b'TJ':
            start = None
            depth = 0
            for idx in range(len(operands) - 1, -1, -1):
                if operands[idx] == ('op', b']'):
                    depth = 1
                elif operands[idx] == ('op', b'['):
                    depth -= 1
                    if depth == 0:
                        start = idx
                        break
            if start is not None:
                for typ2, v2 in operands[start+1:]:
                    if typ2 == 'str':
                        glyphs.extend(emit(v2, tm, ctm, font, fsize))
                        tm = advance(v2, tm, font, fsize)
                    elif typ2 == 'num':
                        tm = mat_mul((1, 0, 0, 1, -v2 / 1000.0 * fsize, 0), tm)
        operands = []
    pages_glyphs.append(glyphs)

# ---------- layout ----------
LIG = {'\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb00': 'ff'}

def layout(glyphs, page_width=612.0):
    glyphs = [g for g in glyphs if g[3] != '']
    if not glyphs:
        return [], [], []
    glyphs.sort(key=lambda g: (-round(g[1], 2), g[0]))
    raw = []
    cur = []
    last_y = None
    for g in glyphs:
        tol = max(0.6, g[2] * 0.16)
        if last_y is None or abs(g[1] - last_y) > tol:
            if cur:
                raw.append(cur)
            cur = [g]
            last_y = g[1]
        else:
            cur.append(g)
    if cur:
        raw.append(cur)

    def render(line):
        line = sorted(line, key=lambda g: g[0])
        s = ''
        last_x = None
        for x, y, size, u, adv in line:
            u = LIG.get(u, u)
            if last_x is not None:
                gap = x - last_x
                if gap > size * 0.19 and not s.endswith(' ') and u != ' ':
                    s += ' '
            s += u
            last_x = x + adv
        return (line[0][1], line[0][0], line[0][2], re.sub(r'  +', ' ', s).strip())

    full, left, right = [], [], []
    for line in raw:
        xmin = min(g[0] for g in line)
        xmax = max(g[0] + g[4] for g in line)
        rec = render(line)
        if xmin < 200 and xmax > 470:
            full.append(rec)
        elif xmin < 310:
            left.append(rec)
        else:
            right.append(rec)

    for lst in (full, left, right):
        lst.sort(key=lambda r: (-r[0], r[1]))
    return full, left, right

all_lines = []
for pi, glyphs in enumerate(pages_glyphs):
    all_lines.append((pi + 1, None, None, f'===== PAGE {pi+1} ====='))
    full, left, right = layout(glyphs)
    if not left and not right:
        seq = full
    else:
        col_y = [r[0] for r in left + right]
        top, bot = max(col_y), min(col_y)
        head = sorted([r for r in full if r[0] > top], key=lambda r: -r[0])
        tail = sorted([r for r in full if r[0] < bot], key=lambda r: -r[0])
        seq = head + left + right + tail
        # mid-page full-width items (e.g. figures/captions) inserted by y
        for r in full:
            if bot <= r[0] <= top:
                idx = len(seq)
                for i, s in enumerate(seq):
                    if s[0] < r[0]:
                        idx = i
                        break
                seq.insert(idx, r)
    for y, x, size, s in seq:
        all_lines.append((pi + 1, y, x, s))

with open('_extracted.txt', 'w', encoding='utf-8') as fh:
    for pi, y, x, s in all_lines:
        if y is None:
            fh.write(f'\n{s}\n')
        else:
            fh.write(f'[p{pi} y={y:6.1f} x={x:5.1f}] {s}\n')

print('pages', len(pages), 'lines', len(all_lines))
print('\n'.join(l[3] for l in all_lines[:60]))
