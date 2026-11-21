#!/usr/bin/env python3
"""按 goroutine ID 统计 pprof 采样，估计平均存活时间占程序总时长的比例。"""
import os, re, sys

def parse_dir(d, total_s):
    files = sorted(f for f in os.listdir(d) if f.endswith('.txt'))
    if not files:
        return None
    # 采样间隔 = 总窗口 / 轮数
    gap = total_s / len(files)
    ids = {}
    for fn in files:
        txt = open(os.path.join(d, fn), errors='ignore').read()
        blocks = re.split(r'(?m)^goroutine ', txt)
        for b in blocks[1:]:
            m = re.match(r'(\d+) \[(.*?)\]:', b)
            if not m:
                continue
            if 'pprof.writeGoroutineStacks' in b:
                continue
            gid = int(m.group(1))
            ids[gid] = ids.get(gid, 0) + 1
    if not ids:
        return None
    lifes = [c * gap / total_s for c in ids.values()]
    lifes.sort()
    n = len(lifes)
    avg = sum(lifes) / n
    med = lifes[n // 2]
    long_ = sum(1 for x in lifes if x >= 0.9) / n
    return dict(files=len(files), goroutines=n, avg=avg, med=med, long90=long_,
                maxl=max(lifes), minl=min(lifes))

if __name__ == '__main__':
    base, label, win, total = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    for side in ('sp', 'cp'):
        d = os.path.join(base, f'{label}_{side}')
        r = parse_dir(d, win)
        name = 'server' if side == 'sp' else 'client'
        if not r:
            print(f'{label} {name}: NO_DATA')
            continue
        print(f"{label} {name}: samples={r['files']} goroutines={r['goroutines']} "
              f"avg_alive={r['avg']*100:.2f}% median={r['med']*100:.2f}% "
              f">=90%={r['long90']*100:.1f}% min={r['minl']*100:.2f}% max={r['maxl']*100:.1f}% "
              f"(normalized by {total:.0f}s program time)")
