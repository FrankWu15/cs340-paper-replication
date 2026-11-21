import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
exec(open('_pdfextract.py', encoding='utf-8').read().split('# ---------- layout ----------')[0])
LIG = {'\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb00': 'ff'}

def seq_page(pnum):
    pbody = obj_of(pnum)
    res = resolve(dict_get(pbody, b'Resources'))
    fontdict = {}
    fd = resolve(dict_get(res, b'Font'))
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

    lines = []
    cur = []
    last_x = None
    last_y = None
    last_sz = None
    ctm = (1, 0, 0, 1, 0, 0)
    tm = (1, 0, 0, 1, 0, 0)
    tlm = tm
    font = None
    fsize = 10.0
    leading = 0.0
    stack = []
    operands = []

    def flush():
        nonlocal cur, last_x, last_y
        if cur:
            s = ''
            for u in cur:
                s += u
            s = re.sub(r'  +', ' ', s).strip()
            if s:
                lines.append(s)
        cur = []
        last_x = None
        last_y = None

    def show(sbytes, tm, ctm, font, fsize, is_super_ok=True):
        nonlocal cur, last_x, last_y, last_sz
        m = mat_mul(tm, ctm)
        scale = (m[0] ** 2 + m[1] ** 2) ** 0.5
        eff = fsize * scale
        x, y = apply(m, 0, 0)
        for ch in sbytes:
            u = None
            if font:
                if ch in font['cmap']:
                    u = font['cmap'][ch]
                elif ch in font['uni']:
                    u = font['uni'][ch]
            if u is None or u == '':
                u = chr(ch) if 32 <= ch < 127 else ''
            u = LIG.get(u, u)
            w = font['widths'].get(ch, 500) if font else 500
            adv = w / 1000.0 * fsize * scale
            if cur:
                if abs(y - last_y) > max(2.2, 0.32 * (last_sz or eff)):
                    flush()
                else:
                    gap = x - last_x
                    if gap > eff * 0.13 and not cur[-1].endswith(' ') and u != ' ':
                        cur.append(' ')
            if not cur:
                last_y = y
                last_sz = eff
            cur.append(u)
            last_x = x + adv
            x += adv

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
                show(sbytes, tm, ctm, font, fsize)
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
                for typ2, v2 in operands[start + 1:]:
                    if typ2 == 'str':
                        show(v2, tm, ctm, font, fsize)
                        tm = advance(v2, tm, font, fsize)
                    elif typ2 == 'num':
                        tm = mat_mul((1, 0, 0, 1, -v2 / 1000.0 * fsize, 0), tm)
        operands = []
    flush()
    return lines

out = []
for i, pnum in enumerate(pages):
    out.append(f'===== PAGE {i+1} =====')
    out.extend(seq_page(pnum))

text = '\n'.join(out)

# de-hyphenate line joins: word- at end followed by lowercase continuation
lines = text.split('\n')
merged = []
for ln in lines:
    if merged and merged[-1].endswith('-') and re.match(r'^[a-z]', ln):
        merged[-1] = merged[-1][:-1] + ln
    elif merged and merged[-1].endswith('-\u2010'):
        pass
    else:
        merged.append(ln)
text2 = '\n'.join(merged)
open('_sequential.txt', 'w', encoding='utf-8').write(text2)
print(text2[:4000])
