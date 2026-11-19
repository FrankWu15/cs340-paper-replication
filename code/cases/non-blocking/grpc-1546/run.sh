#!/usr/bin/env bash
# grpc#1546 —— 并发 WriteStatus 向已关闭的 writes 通道发送
# 判定：buggy FAIL ×N（panic），fixed PASS ×N
#
# 与 p4_case.sh 的差别只有一处：本案例单次命中率不足 1%，每轮必须 -count=200
# 才能稳定触发，而 p4_case.sh 固定 -count=1。其余流程与它一致。
#
# 用法: ./run.sh [count] [iters] [timeout_s]      默认 200 3 120
#   GRPC1546_BUGGY / GRPC1546_FIXED 指定两侧源码目录
#   GO1546 指定 go 可执行文件
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUGGY="${GRPC1546_BUGGY:-$HOME/grpc1546/buggy}"
FIXED="${GRPC1546_FIXED:-$HOME/grpc1546/fixed}"
GOBIN="${GO1546:-/usr/local/go-versions/go1.22.9/bin/go}"
COUNT="${1:-200}"
ITERS="${2:-3}"
TMO="${3:-120}"
FIX=22c3f92f5faea8db492fb0f5ae4daf0d2752b19e
TEST_RE='TestHandlerTransport_HandleStreams_MultiWriteStatus$'
OUT="$HERE/logs"

export GO111MODULE=on
export GOFLAGS=-mod=mod
export GOSUMDB=off
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
# 显式钉住模块缓存：本机 go env 里残留过 GOPATH=/root/go，普通用户下不可写
export GOPATH="${GOPATH:-$HOME/go}"
export GOMODCACHE="${GOMODCACHE:-$HOME/go/pkg/mod}"

[ -x "$GOBIN" ] || { echo "找不到 go: $GOBIN（用 GO1546 指定）"; exit 1; }
mkdir -p "$OUT"

prepare() {   # $1=源码目录 $2=标签
  local dir="$1" label="$2"
  [ -d "$dir/transport" ] || { echo "[$label] 缺少源码目录: $dir"; exit 1; }
  [ -f "$dir/go.mod" ] || cp "$HERE/notes/go.mod" "$dir/go.mod"
  [ -f "$dir/go.sum" ] || cp "$HERE/notes/go.sum" "$dir/go.sum"
  # 缺陷版没有回归测试，只补测试文件，产品代码保持缺陷
  if ! grep -q 'MultiWriteStatus' "$dir/transport/handler_server_test.go"; then
    ( cd "$dir" && patch -p1 -s < "$HERE/patches/1546-test.patch" ) || {
      echo "[$label] 测试补丁应用失败"; exit 1; }
    echo "  [$label] 测试补丁已应用"
  fi
}

run_side() {  # $1=buggy|fixed  $2=源码目录
  local side="$1" dir="$2" i log rc verdict
  local pass=0 fail=0 tmo=0 norun=0 err=0
  cd "$dir" || exit 1
  for i in $(seq 1 "$ITERS"); do
    log="$OUT/grpc_${side}_iter${i}.log"
    timeout $(( TMO * 3 + 90 )) "$GOBIN" test ./transport \
      -run "$TEST_RE" -count="$COUNT" -vet=off -timeout "${TMO}s" > "$log" 2>&1
    rc=$?
    if grep -q 'no tests to run' "$log"; then verdict=NOTRUN; norun=$((norun+1))
    elif grep -q 'test timed out' "$log"; then verdict=TIMEOUT; tmo=$((tmo+1))
    elif grep -qE '^(FAIL|--- FAIL)' "$log"; then verdict=FAIL; fail=$((fail+1))
    elif [ "$rc" -eq 0 ]; then verdict=PASS; pass=$((pass+1))
    else verdict=ERROR; err=$((err+1)); fi
    echo "  [$side] iter$i: $verdict"
  done
  cp "$OUT/grpc_${side}_iter${ITERS}.log" "$OUT/grpc_${side}_last.log"
  echo "  [$side] SUMMARY pass=$pass fail=$fail timeout=$tmo notrun=$norun error=$err"
}

{
  echo "bug=grpc1546"
  echo "sha=$FIX"
  echo "buggy_sha=$(git -C "$BUGGY" rev-parse HEAD 2>/dev/null || echo cf79c849790fd644fab2ef0996e07c177f7b689c)"
  echo "test=$TEST_RE"
  echo "pkg=transport"
  echo "count=$COUNT"
  echo "iters=$ITERS"
  echo "timeout=$TMO"
  echo "date=$(date -Is)"
  echo "goroot=$(dirname "$(dirname "$GOBIN")")"
  "$GOBIN" version
  echo "uname=$(uname -sr) $(uname -m)"
} > "$OUT/env.txt"

{
  echo "############ grpc  fix=$FIX  pkg=transport  test=$TEST_RE  count=$COUNT  iters=$ITERS  timeout=${TMO}s"
  prepare "$BUGGY" buggy
  run_side buggy "$BUGGY"
  prepare "$FIXED" fixed
  run_side fixed "$FIXED"
  echo "############ DONE grpc"
} 2>&1 | tee "$OUT/summary.txt"
