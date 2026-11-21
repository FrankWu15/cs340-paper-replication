#!/usr/bin/env bash
# moby#0d9e543（论文 uid: docker@0d9e5436）—— Stop() 持锁再调 Kill()，同一把 sync.Mutex 重入
#
# 两个程序，两条证据，不要混：
#   code/moby_0d9e543.go        带 2s watchdog → buggy 表现为 TIMEOUT（watchdog 会抑制内置检测器）
#   detector/runtime_deadlock.go 主 goroutine 双重 Lock → 能触发 runtime 的 DEADLOCK
#
# 用法: ./run.sh            （GO=/path/to/go ./run.sh 可指定工具链）
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1
GO="${GO:-go}"
mkdir -p bin logs

echo "### 1. 最小复现 code/moby_0d9e543.go（含 2s watchdog）"
"$GO" build -o bin/repro code/moby_0d9e543.go || { echo "BUILD_FAIL"; exit 1; }
timeout 30 ./bin/repro > logs/repro.log 2>&1
repro_rc=$?
cat logs/repro.log

echo
echo "### 2. 内置检测器对照 detector/runtime_deadlock.go（主 goroutine 双重 Lock）"
"$GO" build -o bin/detector detector/runtime_deadlock.go || { echo "BUILD_FAIL"; exit 1; }
timeout 30 ./bin/detector > logs/detector.log 2>&1
det_rc=$?
cat logs/detector.log

# 判定
if grep -q "Operation timed out after 2 seconds" logs/repro.log; then repro_v=TIMEOUT; else repro_v=NO_TIMEOUT; fi
if grep -q "Completed successfully" logs/repro.log; then repro_f=CLEAN; else repro_f=UNEXPECTED; fi
if grep -q "all goroutines are asleep - deadlock" logs/detector.log; then det_v=DEADLOCK; else det_v=NO_DEADLOCK; fi

{
  echo "case=moby-0d9e543"
  echo "go=$("$GO" version 2>&1 | tr -d '\n')"
  echo "repro_rc=$repro_rc repro_buggy=$repro_v repro_fixed=$repro_f"
  echo "detector_rc=$det_rc detector=$det_v"
} | tee logs/verdict.txt

# 期望：repro_buggy=TIMEOUT、repro_fixed=CLEAN、detector=DEADLOCK
[ "$repro_v" = TIMEOUT ] && [ "$repro_f" = CLEAN ] && [ "$det_v" = DEADLOCK ]
