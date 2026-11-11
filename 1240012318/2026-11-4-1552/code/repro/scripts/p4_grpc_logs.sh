#!/usr/bin/env bash
# 重跑 4 条 grpc 复现，把每条的原始 go test 输出按 bug 分目录留存
set -u

R=$HOME/gopath/src/google.golang.org/grpc
S=$HOME/repro-out/p4_case.sh
OUT=$HOME/grpc_logs
ITERS=${ITERS:-3}

# p4_case.sh 在子进程里 export，本脚本自己要记录环境，需单独钉住
export GOROOT=/usr/local/go1.10.8

mkdir -p "$OUT"
cd "$R" || exit 1

# 先确保仓库干净，避免残留补丁影响结果
git checkout -f -- . >/dev/null 2>&1
git clean -fd >/dev/null 2>&1

run_one() {
  local name=$1 sha=$2 test=$3 pkg=$4 to=$5
  echo "=============================================================="
  echo "### $name  sha=$sha  pkg=$pkg  timeout=${to}s  iters=$ITERS"
  echo "=============================================================="
  mkdir -p "$OUT/$name"
  # 清掉上一轮的 tmp 日志，避免混淆
  rm -f /tmp/grpc_*.log

  bash "$S" "$R" "$sha" "$test" "$pkg" "$ITERS" "$to" 2>&1 | tee "$OUT/$name/summary.txt"

  # 归档本轮的逐次原始输出
  cp /tmp/grpc_buggy_iter*.log /tmp/grpc_fixed_iter*.log "$OUT/$name/" 2>/dev/null
  cp /tmp/grpc_buggy_last.log /tmp/grpc_fixed_last.log "$OUT/$name/" 2>/dev/null

  # 记录当时的环境
  {
    echo "bug=$name"
    echo "sha=$sha"
    echo "test=$test"
    echo "pkg=$pkg"
    echo "iters=$ITERS"
    echo "timeout=$to"
    echo "date=$(date -Iseconds)"
    echo "goroot=$GOROOT"
    "$GOROOT/bin/go" version
    echo "uname=$(uname -srm)"
  } > "$OUT/$name/env.txt"

  echo
}

run_one grpc793  5a547ed72c09faf4050739d54caea1d51f4d276d "TestServerGracefulStopIdempotent\$"                      test      30
run_one grpc1293 7df48bee8829276b13ef52bff4e1c47b9d55cd7d "TestInflightStreamClosing\$"                               transport 60
run_one grpc1424 4e56696c6c5a8cd7b711a1eb8936463559361da5 "TestClientLBWatcherWithClosedBalancer\$"                   .         60
run_one grpc1687 c6b46087ab923e9f453ec433f99174cdd45b9b89 "TestHandlerTransport_HandleStreams_WriteStatusWrite\$"     transport 60

echo "=============================================================="
echo "全部完成，日志在 $OUT"
find "$OUT" -type f | sort
echo "=============================================================="
