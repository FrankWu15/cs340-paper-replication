#!/usr/bin/env bash
# _paths.sh —— 统一路径解析，所有脚本 source 这个文件。
#
# 目的：满足课程评分表里「不得硬编码路径」的要求 —— 换机器、换目录名都不需要改脚本。
# 优先级：环境变量 > local.env > 项目内自动探测 > 报错
#
# 用法（在脚本里）：
#   source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"
#   echo "$REPO_ROOT"   # 上游仓库目录（repos/ 或 6app/ 都认）
#
# 机器相关配置（Go 工具链、二进制目录）写在 repro/local.env，该文件不进版本库。
# 模板见 repro/local.env.example。

set -u

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPRO_DIR="$(cd "$_HERE/.." && pwd)"
PROJECT_DIR="$(cd "$REPRO_DIR/.." && pwd)"

# 机器相关覆盖（可选）
if [[ -f "$REPRO_DIR/local.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPRO_DIR/local.env"
fi

# ---- 上游仓库目录：默认在项目根下，避开「必须叫 repos」的假设 ----------------
if [[ -z "${REPO_ROOT:-}" ]]; then
  for _cand in repos 6app upstream-repos src; do
    if [[ -d "$PROJECT_DIR/$_cand" ]]; then
      REPO_ROOT="$PROJECT_DIR/$_cand"
      break
    fi
  done
fi
if [[ -z "${REPO_ROOT:-}" ]]; then
  echo "[!] 找不到上游仓库目录。请在项目根下放置 repos/ 或 6app/，或设置 REPO_ROOT。" >&2
  REPO_ROOT="$PROJECT_DIR/repos"
fi

# ---- 其余目录 ---------------------------------------------------------------
LOG_DIR="${LOG_DIR:-$REPRO_DIR/logs}"     # pin 表、克隆日志
OUT_DIR="${OUT_DIR:-$REPRO_DIR/out}"      # 报告与中间结果
DATA_DIR="${DATA_DIR:-$REPRO_DIR/data}"   # 解析后的数据表
# 二进制不默认放在 Desktop 下：Windows 上自编译 exe 在 Desktop 里会 winapi error #5
BIN_DIR="${BIN_DIR:-${TMPDIR:-/tmp}/go-concurrency-bugs-bin}"

# ---- Go 工具链：未指定则用 PATH 里的 go ------------------------------------
GO_MODERN="${GO_MODERN:-$(command -v go 2>/dev/null || true)}"
GO_LEGACY="${GO_LEGACY:-}"

export REPRO_DIR PROJECT_DIR REPO_ROOT LOG_DIR OUT_DIR DATA_DIR BIN_DIR GO_MODERN GO_LEGACY
