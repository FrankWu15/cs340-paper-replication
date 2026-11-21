#!/usr/bin/env bash
# grpc#1424 —— DialContext 里 lbWatcher 泄漏，doneChan 永不关闭（补丁自带回归测试）
# 判定：buggy FAIL ×N，fixed PASS ×N
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  4e56696c6c5a8cd7b711a1eb8936463559361da5 \
  "TestClientLBWatcherWithClosedBalancer$" . \
  "${1:-3}" "${2:-60}"
