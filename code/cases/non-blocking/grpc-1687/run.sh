#!/usr/bin/env bash
# grpc#1687 —— handler server 重复 WriteStatus 导致 send on closed channel
# 判定：buggy FAIL ×N（panic），fixed PASS ×N
# 注意：包目录必须是 transport，不是 test
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  c6b46087ab923e9f453ec433f99174cdd45b9b89 \
  "TestHandlerTransport_HandleStreams_WriteStatusWrite$" transport \
  "${1:-3}" "${2:-60}"
