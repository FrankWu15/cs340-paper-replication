#!/usr/bin/env bash
# _paths.sh —— 统一路径解析，所有分析脚本 source 这个文件。
#
# 目录约定（本仓库固定结构，不写死任何绝对路径）：
#
#   <root>/
#   ├── data/           输入数据（CSV、repo.lock.tsv）
#   ├── results/        产出（data/ 表、logs/ 日志、shots/ 截图）
#   └── code/
#       ├── analysis/   ← 本文件所在目录
#       ├── harness/    单条 bug 复现驱动
#       └── tools/      goast 统计器
#
# 上游 6 个仓库与论文 artifact 体积大、不入库，按以下顺序查找：
#   1. 环境变量 REPO_ROOT / ARTIFACT_DIR
#   2. local.env（不进版本库，模板见 code/analysis/local.env.example）
#   3. <root>/6app、<root>/artifact
#   4. <root>/../6app、<root>/../go-concurrency-bugs-master（同级目录回退）

set -u

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$_HERE/../.." && pwd)"   # code/analysis -> <root>
DATA_DIR="${DATA_DIR:-$PROJECT_DIR/data}"
OUT_DIR="${OUT_DIR:-$PROJECT_DIR/results/data}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/results/logs/_meta}"

# 机器相关覆盖（可选）
if [[ -f "$_HERE/local.env" ]]; then
  # shellcheck disable=SC1091
  source "$_HERE/local.env"
fi

# ---- 上游仓库目录 -----------------------------------------------------------
if [[ -z "${REPO_ROOT:-}" ]]; then
  for _cand in "$PROJECT_DIR/6app" "$PROJECT_DIR/../6app" \
               "$PROJECT_DIR/repos" "$PROJECT_DIR/../repos"; do
    if [[ -d "$_cand" ]]; then
      REPO_ROOT="$(cd "$_cand" && pwd)"
      break
    fi
  done
fi
if [[ -z "${REPO_ROOT:-}" ]]; then
  echo "[!] 找不到上游仓库目录。请跑 make setup-repos，或设置 REPO_ROOT。" >&2
  REPO_ROOT="$PROJECT_DIR/6app"
fi

# ---- 论文 artifact（169 个补丁原文）----------------------------------------
if [[ -z "${ARTIFACT_DIR:-}" ]]; then
  for _cand in "$PROJECT_DIR/artifact" "$PROJECT_DIR/../go-concurrency-bugs-master"; do
    if [[ -d "$_cand" ]]; then
      ARTIFACT_DIR="$(cd "$_cand" && pwd)"
      break
    fi
  done
fi
ARTIFACT_DIR="${ARTIFACT_DIR:-$PROJECT_DIR/artifact}"

# 二进制不放在桌面目录下：Windows 上自编译 exe 在 Desktop 里会 winapi error #5
BIN_DIR="${BIN_DIR:-${TMPDIR:-/tmp}/go-concurrency-bugs-bin}"

# ---- Go 工具链：未指定则用 PATH 里的 go ------------------------------------
GO_MODERN="${GO_MODERN:-$(command -v go 2>/dev/null || true)}"
GO_LEGACY="${GO_LEGACY:-}"

mkdir -p "$OUT_DIR" "$LOG_DIR" "$BIN_DIR" 2>/dev/null || true

export _HERE PROJECT_DIR DATA_DIR OUT_DIR LOG_DIR REPO_ROOT ARTIFACT_DIR BIN_DIR
export GO_MODERN GO_LEGACY
