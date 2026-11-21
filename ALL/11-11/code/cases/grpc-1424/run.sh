#!/usr/bin/env bash
# grpc#1424 —— balancer 关闭后 doneChan 永不关闭（blocking）
# 判定：buggy FAIL（clientconn_test.go:390 100ms 内未关闭），fixed PASS
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  4e56696c6c5a8cd7b711a1eb8936463559361da5 \
  "TestClientLBWatcherWithClosedBalancer$" . "${1:-3}" "${2:-60}"
