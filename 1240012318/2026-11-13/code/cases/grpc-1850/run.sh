#!/usr/bin/env bash
# grpc#1850 —— 客户端发送配额泄漏，写大消息卡到 deadline（补丁自带官方测试）
#
# 单次命中率只有 16%~20%，这个脚本的默认 3 轮基本全 PASS，看不到 bug。
# 要复现请用 run_loop.sh（50 次循环）。
#
# 注意：本机 tcp-tls / handler 环境不可用（TLS 握手卡在 Dial），只跑 tcp-clear
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"
# 官方测试支持 -only_env，这台机器上只有 tcp-clear 干净（tcp-tls / no-balancer 会卡在 Dial）
P4_EXTRA_ARGS="-args -only_env=tcp-clear" bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  484b3ebb4ab56d3decc8240d599718bdbefcf7eb \
  "TestClientDoesntDeadlockWhileWritingErrornousLargeMessages$" test \
  "${1:-3}" "${2:-60}"
