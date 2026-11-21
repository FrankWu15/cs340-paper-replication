#!/usr/bin/env bash
# grpc#1687 —— 向已关闭的 chan 发送（非阻塞，必现 panic）
# 判定：buggy FAIL（panic: send on closed channel，handler_server.go:170），fixed PASS
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  c6b46087ab923e9f453ec433f99174cdd45b9b89 \
  "TestHandlerTransport_HandleStreams_WriteStatusWrite$" transport "${1:-3}" "${2:-60}"
