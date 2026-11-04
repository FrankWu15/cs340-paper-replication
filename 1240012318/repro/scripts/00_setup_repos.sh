#!/usr/bin/env bash
# P0：克隆 6 个上游仓库并冻结到论文的数据收集日（2018-05-21）。
#
# 关键点：
#   * 用 2018-05-22 作为 --before 上界，才能包含 2018-05-21 全天的 commit。
#     论文 Table 1 的 Date 列就是 2018-05-21，BoltDB 在该日切出恰好 816 个 commit，可作校准。
#   * clone 时直接带上 core.longpaths / core.autocrlf，避免 Kubernetes/CockroachDB 的深路径
#     和 CRLF 转换破坏 P4 的补丁行号；只作用于本仓库，不改全局 config。
#   * 克隆失败自动重试 3 次（穿代理时偶发 connect timeout）。
#
# 用法:
#   ./scripts/00_setup_repos.sh                 # 克隆到 team/repos（脚本位置自动推导）
#   ROOT=/d/repos ./scripts/00_setup_repos.sh   # 换目录
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$REPO_ROOT"
SNAP="${SNAP:-2018-05-22}"
LOG="$LOG_DIR"
mkdir -p "$ROOT" "$LOG"

# app|url|论文 commit 数|论文 LOC|克隆方式
#   full  = 完整历史 + 工作区（小仓库，便于离线复现）
#   treeless = --filter=tree:0 --no-checkout（大仓库：只拉 commit 对象，不拉 tree/blob）
#     原因：moby / cockroach / kubernetes 的完整 pack 有 1GB+，在代理下反复中断、每次重试都要从头来；
#     实测 moby 用 tree:0 只有 31MB。P1 的 git log --grep 只需要 commit 对象；
#     P2/P4 真要读代码时，再对某个 commit 单独 `git checkout`（按需拉取，见文末提示）。
SPECS=(
  "boltdb|https://github.com/boltdb/bolt.git|816|9060|full"
  "etcd|https://github.com/etcd-io/etcd.git|14101|441999|full"
  "grpc-go|https://github.com/grpc/grpc-go.git|2528|53076|full"
  "docker|https://github.com/moby/moby.git|35149|786174|treeless"
  "cockroachdb|https://github.com/cockroachdb/cockroach.git|29485|520967|treeless"
  "kubernetes|https://github.com/kubernetes/kubernetes.git|65684|2297729|treeless"
)

WANT=("$@")   # 只处理指定的 app；空则全部

[[ -f "$LOG/repos.tsv" ]] || printf "app\tcommit\tdate\tcommits\tpaper_commits\tdiff\tmode\tchecked_out\n" > "$LOG/repos.tsv"

clone_one() {
  local app=$1 url=$2 mode=${3:-full}
  local dir="$ROOT/$app"
  if [[ -d "$dir/.git" ]]; then
    echo "[=] $app 已存在，跳过克隆"
    return 0
  fi
  local extra=()
  case "$mode" in
    treeless) extra=(--filter=tree:0 --no-checkout) ;;
    partial)  extra=(--filter=blob:none) ;;
  esac
  for attempt in 1 2 3; do
    echo "[>] $app 克隆（$mode，第 $attempt 次）"
    if git -c core.longpaths=true -c core.autocrlf=false \
         -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 \
         clone --quiet "${extra[@]}" "$url" "$dir" 2>>"$LOG/clone_$app.err"; then
      return 0
    fi
    rm -rf "$dir"
    sleep 5
  done
  echo "[x] $app 克隆失败，见 $LOG/clone_$app.err"
  return 1
}

for spec in "${SPECS[@]}"; do
  IFS='|' read -r app url paper_commits paper_loc mode <<< "$spec"
  if [[ ${#WANT[@]} -gt 0 ]]; then
    hit=0
    for w in "${WANT[@]}"; do [[ "$w" == "$app" ]] && hit=1; done
    [[ $hit -eq 0 ]] && continue
  fi
  clone_one "$app" "$url" "$mode" || continue
  dir="$ROOT/$app"

  git -C "$dir" config core.longpaths true
  git -C "$dir" config core.autocrlf false

  # 必须加 --first-parent：沿着主线找该日期的最后一个 commit。
  # 不加的话会挑到「同一天合并进来的侧分支 commit」，它的祖先链可能很短，
  # rev-list --count 会严重偏小（moby 实测 2560，而正确值是 35151）。
  sha=$(git -C "$dir" rev-list -1 --first-parent --before="$SNAP" HEAD 2>/dev/null)
  if [[ -z "$sha" ]]; then
    echo "[x] $app 找不到 $SNAP 之前的 commit"
    continue
  fi

  checked=0
  if [[ "$mode" != "treeless" ]]; then
    git -C "$dir" checkout --quiet "$sha" || { echo "[x] $app checkout 失败"; continue; }
    checked=1
  fi

  commits=$(git -C "$dir" rev-list --count "$sha")
  date=$(git -C "$dir" log -1 --format=%ad --date=short "$sha")
  diff=$(( commits - paper_commits ))

  # 同一 app 重跑时覆盖旧行，避免 TSV 里出现重复记录
  awk -F'\t' -v a="$app" 'NR==1 || $1 != a' "$LOG/repos.tsv" > "$LOG/repos.tsv.tmp" \
    && mv "$LOG/repos.tsv.tmp" "$LOG/repos.tsv"
  printf "%s\t%s\t%s\t%s\t%s\t%+d\t%s\t%s\n" \
    "$app" "${sha:0:12}" "$date" "$commits" "$paper_commits" "$diff" "$mode" "$checked" >> "$LOG/repos.tsv"
  echo "[ok] $app  ${sha:0:8}  $date  commits=$commits (论文 $paper_commits, ${diff:+$diff})  mode=$mode checkout=$checked"
done

echo
echo "=== 结果 ==="
column -t -s $'\t' "$LOG/repos.tsv" 2>/dev/null || cat "$LOG/repos.tsv"
du -sh "$ROOT"/* 2>/dev/null
echo
echo "[注意] 本脚本钉的是「含 2018-05-21 全天」的上界，commit 数会略多于论文。"
echo "       要精确对齐论文的 commit 数，接着跑： bash scripts/00_pin_exact.sh"
