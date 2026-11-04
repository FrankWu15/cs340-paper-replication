#!/usr/bin/env bash
# 补齐 P0 阶段未完成的两个仓库（cockroachdb / kubernetes），
# 并把 docker 的 treeless 仓库 checkout 出 2018 快照的文件内容。
#
# 用法: bash 00_finish_downloads.sh
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$REPO_ROOT"
LOG="$LOG_DIR"
DOCKER_PIN="${DOCKER_PIN:-9bd5d9912f0c}"
mkdir -p "$LOG"

stamp() { date '+%F %T'; }

echo "=== $(stamp) 开始 ==="

for app in cockroachdb kubernetes; do
  if [[ -d "$ROOT/$app/.git" ]]; then
    echo "[=] $app 已存在，跳过克隆"
    continue
  fi
  echo "[>] $(stamp) 克隆 $app（treeless，只拉 commit 对象）"
  bash "$HERE/00_setup_repos.sh" "$app"
  rc=$?
  if [[ $rc -eq 0 && -d "$ROOT/$app/.git" ]]; then
    echo "[ok] $app commits=$(git -C "$ROOT/$app" rev-list --count HEAD) size=$(du -sh "$ROOT/$app" | cut -f1)"
  else
    echo "[x] $app 失败（rc=$rc），详见 $LOG/clone_$app.err"
  fi
done

# docker: 补全工作区文件（treeless clone 只有 commit 对象）
if [[ -d "$ROOT/docker/.git" ]]; then
  echo "[>] $(stamp) docker checkout $DOCKER_PIN（按需拉取该版本 blob）"
  if git -C "$ROOT/docker" -c core.longpaths=true -c core.autocrlf=false \
       checkout --quiet "$DOCKER_PIN" 2>>"$LOG/docker_checkout.err"; then
    echo "[ok] docker 文件数=$(ls "$ROOT/docker" | grep -v '^\.git$' | wc -l) size=$(du -sh "$ROOT/docker" | cut -f1)"
  else
    echo "[x] docker checkout 失败，见 $LOG/docker_checkout.err"
  fi
else
  echo "[!] docker 目录不存在，跳过"
fi

echo "=== $(stamp) 完成 ==="
du -sh "$ROOT"/* 2>/dev/null
