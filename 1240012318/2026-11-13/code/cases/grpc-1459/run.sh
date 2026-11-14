#!/usr/bin/env bash
# grpc#1459 —— client keepalive 唤醒令牌未复位，持 t.mu 阻塞导致后续 RPC 死锁
# 判定：buggy 第 3 次 RPC 起永久挂起（TIMEOUT），fixed 4 次全 PASS
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_probe.sh" "$REPO" \
  c29d6389e66f5da1a226df88607857aab4db9f7a \
  . "TestKeepaliveAwakenDeadlockProbe$" "$HERE/probe" \
  "${1:-3}" "${2:-30}" norace
