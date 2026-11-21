# -*- coding: utf-8 -*-
import re, io

src = open('_sequential.txt', encoding='utf-8').read()
i = src.index('References')
body = src[i + len('References'):]
lines = [l.strip() for l in body.split('\n') if l.strip()]
entries = []
cur = ''
for ln in lines:
    if re.match(r'^\[\d+\]', ln):
        if cur:
            entries.append(cur.strip())
        cur = ln
    else:
        cur += ' ' + ln
if cur:
    entries.append(cur.strip())

out = []
FIX = [
    ('InProceedings', 'In Proceedings'),
    ('InProceedings', 'In Proceedings'),
    ('InProceedings of', 'In Proceedings of'),
    ('goapis', 'go-apis'),
    ('swtch.com/ rsc', 'swtch.com/rsc'),
    ('Peter" Thiemann', 'Peter Thiemann'),
    ('Reno/-Tahoe', 'Reno/Tahoe'),
    ('OSDI\u201912', 'OSDI \u201912'),
]
for e in entries:
    e = re.sub(r'\s+', ' ', e).strip()
    for a, b in FIX:
        e = e.replace(a, b)
    e = re.sub(r'In ?Proceedings', 'In Proceedings', e)
    e = e.replace('Productionrun', 'Production-run')
    e = re.sub(r'(?<=[a-z0-9\)])\.(?=[A-Z])', '. ', e)
    out.append(e)

with io.open('refs_data.py', 'w', encoding='utf-8') as fh:
    fh.write('# -*- coding: utf-8 -*-\nREFS = [\n')
    for e in out:
        fh.write('    %r,\n' % e)
    fh.write(']\n')
print('entries', len(out))
print(out[0])
print(out[-1])
