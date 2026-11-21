#!/usr/bin/env bash
# moby#2d21996（论文 uid: Moby#16309）—— volumeStore 的 Count()/List() 未加锁读共享 map
#
# 需要 -race，且需要 cgo/gcc：
#   Linux / WSL2 直接可用；
#   Windows 本机会报 0xc0000139（缺运行时 DLL），必须在 Linux 里跑。
#
# 用法: ./run.sh            （GO=/path/to/go ./run.sh 可指定工具链）
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1
GO="${GO:-go}"
mkdir -p bin logs

echo "### 构建 -race 版本"
"$GO" build -race -o bin/race code/volume_race.go || { echo "BUILD_FAIL（本机无 cgo/gcc 时属预期）"; exit 1; }

: > logs/verdict.txt
for mode in count list; do
  for side in before after; do
    log="logs/${mode}-${side}.log"
    timeout 180 ./bin/race "$mode" "$side" > "$log" 2>&1
    rc=$?
    races=$(grep -c "WARNING: DATA RACE" "$log" 2>/dev/null || true)
    mapw=$(grep -c "concurrent map iteration and map write" "$log" 2>/dev/null || true)
    done_ok=$(grep -c "Test completed" "$log" 2>/dev/null || true)
    printf '%-6s %-7s rc=%-3s data_race=%-2s map_write=%-2s completed=%s\n' \
      "$mode" "$side" "$rc" "$races" "$mapw" "$done_ok" | tee -a logs/verdict.txt
  done
done

echo
echo "期望：before 侧 data_race>=1（list 还会附带 map_write>=1）；after 侧 data_race=0 且 completed=1"
