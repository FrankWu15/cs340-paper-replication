#!/usr/bin/env bash
# grpc#793 —— 二次 GracefulStop 自我死锁（补丁自带官方测试）
# 判定：buggy TIMEOUT ×N，fixed PASS ×N
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  5a547ed72c09faf4050739d54caea1d51f4d276d \
  "TestServerGracefulStopIdempotent$" test \
  "${1:-3}" "${2:-30}"
