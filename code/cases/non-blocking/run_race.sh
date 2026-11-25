#!/usr/bin/env bash
# 三条 minimal non-blocking 案例的重跑脚本：不变量 + 数据竞争检测器
#
#   2026-11-25 用它在 Ubuntu 18.04 虚拟机（ubuntu1804-p4）上补齐了
#   moby-28682 / kubernetes-36377 / cockroachdb-17112 的 -race 证据。
#   本机 Windows 上 -race 产物启动即 0xC0000139（缺 race 运行时 DLL），必须 Linux。
#
# 用法（在 code/cases/non-blocking/ 下）：
#   bash run_race.sh                                   # 三条，10 轮不变量 + 100 轮 -race
#   CASES=moby-28682 RUNS=10 RACE_RUNS=100 bash run_race.sh
#   SUBDIR=vm-1125 bash run_race.sh                    # 指定落盘子目录（默认 vm-1125）
#
# A 段：不带 -race，看程序自己的不变量，失败退出码 3
# B 段：go build -race，GORACE=halt_on_error=1（首次报告即停，避免刷屏；
#       只影响一轮报几条，不影响这一轮报不报），命中即算检出
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GO="${GO:-go}"
RUNS="${RUNS:-10}"
RACE_RUNS="${RACE_RUNS:-100}"
SUBDIR="${SUBDIR:-vm-1125}"
CASES="${CASES:-moby-28682 kubernetes-36377 cockroachdb-17112}"

echo "# $(date -Is)  go=$("$GO" version)  runs=$RUNS  race_runs=$RACE_RUNS" | tee "$ROOT/${SUBDIR}-summary.txt"

for c in $CASES; do
  d="$ROOT/$c"
  [ -d "$d" ] || { echo "缺目录 $d"; continue; }
  out="$d/logs/$SUBDIR"
  mkdir -p "$out/invariant" "$out/race" "$d/bin"
  echo "================ $c"

  for side in buggy fixed; do
    if ! "$GO" build -o "$d/bin/$side.inv" "$d/$side/main.go" 2> "$out/invariant/build_$side.err"; then
      echo "$c invariant $side BUILD_FAIL"; tail -3 "$out/invariant/build_$side.err"; continue
    fi
    fails=0
    for i in $(seq 1 "$RUNS"); do
      timeout -k 5 120 "$d/bin/$side.inv" > "$out/invariant/${side}_run${i}.log" 2>&1
      [ $? -ne 0 ] && fails=$((fails + 1))
    done
    head="$(grep -m1 -E 'VERDICT|fatal error' "$out/invariant/${side}_run1.log" | tr -d '\r')"
    printf '%-18s invariant %-5s fail=%d/%d  %s\n' "$c" "$side" "$fails" "$RUNS" "$head" | tee -a "$ROOT/${SUBDIR}-summary.txt"
  done

  for side in buggy fixed; do
    if ! "$GO" build -race -o "$d/bin/$side.race" "$d/$side/main.go" 2> "$out/race/build_$side.err"; then
      echo "$c race $side BUILD_FAIL"; tail -3 "$out/race/build_$side.err"; continue
    fi
    hits=0; first="-"
    pat='WARNING: DATA RACE|fatal error: concurrent map'
    : > "$out/race/hits_$side.txt"
    for i in $(seq 1 "$RACE_RUNS"); do
      GORACE="halt_on_error=1" timeout -k 5 180 "$d/bin/$side.race" > "$out/race/${side}_run${i}.log" 2>&1
      rc=$?
      if grep -qE "$pat" "$out/race/${side}_run${i}.log"; then
        hits=$((hits + 1)); [ "$first" = "-" ] && first="$i"
        printf 'run%-4d HIT   exit=%d\n' "$i" "$rc" >> "$out/race/hits_$side.txt"
        [ -f "$out/race/sample_$side.log" ] || cp "$out/race/${side}_run${i}.log" "$out/race/sample_$side.log"
      else
        printf 'run%-4d clean exit=%d  %s\n' "$i" "$rc" "$(grep -m1 -E 'VERDICT|fatal error' "$out/race/${side}_run${i}.log" | tr -d '\r')" >> "$out/race/hits_$side.txt"
      fi
    done
    printf '%-18s race      %-5s hit=%d/%d first=%s\n' "$c" "$side" "$hits" "$RACE_RUNS" "$first" | tee -a "$ROOT/${SUBDIR}-summary.txt"
  done
done
