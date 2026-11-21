#!/usr/bin/env bash
# boltdb@7fb06fee —— 并发读写导致 meta 撕裂（非阻塞，概率触发）
# 判定：统计 10 轮 -race 结果，buggy 失败率 80~100%，fixed 0~10%
# 说明：官方测试用 -run Parallel 整包匹配，不是单条测试
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
# 该脚本是两个 boltdb bug 的批处理，跑完 341 与 7fb06fee 两侧
OUT="${OUT:-$HOME/repro-out}" REPRO_ITERS="${1:-10}" \
  bash "$ROOT/code/harness/08_repro_boltdb.sh"
