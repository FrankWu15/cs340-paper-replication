#!/usr/bin/env bash
# grpc#1850 —— 客户端发送配额泄漏（写大消息卡到 deadline）
#
# 这条 bug 是按概率触发：单次跑官方测试约 16%~20% 命中，3 次循环基本看不出来。
# 所以单独给一个 N 次循环的入口。
#
# 判定（P4_DEADLINE_HIT=1 打开）：
#   DEADLINE → 输出里有 DeadlineExceeded，说明 RPC 卡在写操作上直到测试自身 10s deadline
#              → buggy 侧命中
#   PASS     → 拿到期望的 ResourceExhausted
# fixed 侧应全 PASS。
#
# 用法: bash run_loop.sh [循环次数=50] [单次timeout秒=40]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
REPO="${P4_REPO:-$HOME/gopath/src/google.golang.org/grpc}"

P4_DEADLINE_HIT=1 P4_EXTRA_ARGS="-args -only_env=tcp-clear" bash "$ROOT/code/harness/p4_case.sh" "$REPO" \
  484b3ebb4ab56d3decc8240d599718bdbefcf7eb \
  "TestClientDoesntDeadlockWhileWritingErrornousLargeMessages\$" test \
  "${1:-50}" "${2:-40}"
