#!/usr/bin/env bash
# 编译本目录的 buggy 与 fixed 两侧，各跑 N 次，落日志并给出判定。
#
#   bash run.sh
#   RUNS=10 bash run.sh
#
# 判定约定：程序把结论写在首行——
#   VERDICT: DEADLOCK   卡住超过阈值     退出码 2
#   VERDICT: BUG        逻辑断言失败     退出码 3
#   VERDICT: OK         正常完成         退出码 0
set -u

RUNS="${RUNS:-3}"
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="$(basename "$D")"

mkdir -p "$D/bin" "$D/logs" "$D/results"
cd "$D" || exit 9

echo "=== $CASE (runs=$RUNS) ==="

for side in buggy fixed; do
  if ! go build -o "bin/$side.exe" "$side/main.go" 2> "logs/build_$side.err"; then
    echo "编译失败: $side"; tail -5 "logs/build_$side.err"; exit 9
  fi
  rm -f "logs/build_$side.err"
done

declare -A fails

for side in buggy fixed; do
  fails[$side]=0
  for i in $(seq 1 "$RUNS"); do
    out="logs/${side}_run${i}.log"
    ./"bin/$side.exe" > "$out" 2>&1
    rc=$?
    line="$(grep -m1 -E 'VERDICT|fatal error|missed_close_stdin|trials=' "$out" || head -1 "$out")"
    printf '%s\n' "$line" > "logs/${side}_run${i}.verdict"
    printf 'exit=%d\n' "$rc" >> "logs/${side}_run${i}.verdict"
    if [ "$rc" -ne 0 ]; then fails[$side]=$((fails[$side] + 1)); fi
    printf '  %-5s run%d  exit=%d  %s\n' "$side" "$i" "$rc" "$line"
  done
done

cat > results/verdict.txt <<VERDICT
case: $CASE
runs per side: $RUNS
buggy failures: ${fails[buggy]}/$RUNS
fixed failures: ${fails[fixed]}/$RUNS

VERDICT

if [ "${fails[buggy]}" -ge 1 ] && [ "${fails[fixed]}" -eq 0 ]; then
  echo "REPRODUCED" >> results/verdict.txt
  echo "REPRODUCED  (buggy ${fails[buggy]}/$RUNS 出问题, fixed 0/$RUNS)"
elif [ "${fails[buggy]}" -eq 0 ]; then
  echo "NOT REPRODUCED — buggy 侧未出问题" >> results/verdict.txt
  echo "NOT REPRODUCED (buggy 0/$RUNS)"
else
  echo "INCONCLUSIVE — fixed 侧也有失败" >> results/verdict.txt
  echo "INCONCLUSIVE (fixed ${fails[fixed]}/$RUNS)"
fi
