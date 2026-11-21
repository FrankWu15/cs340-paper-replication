#!/usr/bin/env bash
# grpc#1293 —— 删除在途流不通知调用方（blocking）
# 判定：buggy FAIL（transport_test.go:418 等不到 StreamError），fixed PASS
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  7df48bee8829276b13ef52bff4e1c47b9d55cd7d \
  "TestInflightStreamClosing$" transport "${1:-3}" "${2:-60}"
