#!/usr/bin/env bash
# grpc#1667 —— ccBalancerWrapper.subConns 无同步 map（数据竞态）
# 判定：buggy 检出 DATA RACE，fixed 干净通过
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
bash "$ROOT/code/harness/p4_probe.sh" "$REPO" \
  a62701e4aa1d276bec70311251d62a478404d63f \
  . "TestBalancerSubConnsMapRaceProbe$" "$HERE/probe" \
  "${1:-3}" "${2:-30}" race
