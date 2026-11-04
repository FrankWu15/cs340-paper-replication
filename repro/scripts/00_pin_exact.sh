#!/usr/bin/env bash
# P0 补充：把每个仓库的切点精确钉到「commit 数与论文一致（或最接近）」的那一个 commit。
#
# 背景：论文 Table 1 的 Date 列是 2018-05-21，但论文里的 commit 数是作者在
#   2018-05-21 当天某个时刻 clone 出来的，不是当天结束时的数。
#   用 --before=2018-05-22 取到的是「含 5-21 全天」的上界，必然系统性偏大
#   （实测 kubernetes +41、cockroachdb +41、docker +11、etcd +6、grpc-go +3）。
#
# 做法：从 5-21 上界那个 commit 沿 first-parent 往回走，逐步算 rev-list --count，
#   找到计数最接近论文值的 commit。first-parent 链上的计数单调不减（普通提交 +1，
#   merge 提交 +1+侧分支提交数），所以往回走计数单调下降，可以线性收敛。
#
# 输出：$LOG_DIR/pin_exact.tsv（默认为 repro/logs/）
#   app  cut_commit  cut_count  exact_commit  exact_count  paper  delta  kind
#   kind: exact = 计数与论文完全相等；near = 无法相等，取最接近的一个
#
# 用法:
#   ./scripts/00_pin_exact.sh                 # 全部
#   ./scripts/00_pin_exact.sh kubernetes      # 指定仓库
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$REPO_ROOT"
LOG="$LOG_DIR"
SNAP="${SNAP:-2018-05-22}"
OUT="$LOG/pin_exact.tsv"

# app|论文 commit 数
declare -A PAPER=(
  [boltdb]=816
  [etcd]=14101
  [grpc-go]=2528
  [docker]=35149
  [cockroachdb]=29485
  [kubernetes]=65684
)
ORDER=(boltdb etcd grpc-go docker cockroachdb kubernetes)

WANT=("$@")
pick() {
  local want=$1; shift
  [[ ${#WANT[@]} -eq 0 ]] && return 0
  local w; for w in "${WANT[@]}"; do [[ "$w" == "$want" ]] && return 0; done
  return 1
}

# 结果文件保留历史：已有的行不重算（重算会把「上界 → 精确」的推导记录覆盖成
# 「HEAD 已在切点上」这种无信息状态）。想重算就先删掉这一行或整个文件。
[[ -f "$OUT" ]] || printf "app\tcut_commit\tcut_count\texact_commit\texact_count\tpaper\tdelta\tkind\n" > "$OUT"

for app in "${ORDER[@]}"; do
  pick "$app" || continue
  dir="$ROOT/$app"
  [[ -d "$dir/.git" ]] || { echo "[x] $app 未克隆，跳过"; continue; }
  if grep -q "^$app	" "$OUT" 2>/dev/null; then
    echo "[=] $app 已有记录，跳过（要重算请删掉 $OUT 里对应行）"
    continue
  fi
  target=${PAPER[$app]}

  cut=$(git -C "$dir" rev-list -1 --first-parent --before="$SNAP" HEAD 2>/dev/null)
  [[ -z "$cut" ]] && { echo "[x] $app 找不到切点"; continue; }
  cut_count=$(git -C "$dir" rev-list --count "$cut")

  if (( cut_count < target )); then
    echo "[!] $app 上界 $cut_count 已低于论文 $target，无法回溯"
    printf "%s\t%s\t%s\t-\t-\t%s\t-\tunderflow\n" \
      "$app" "${cut:0:12}" "$cut_count" "$target" >> "$OUT"
    continue
  fi

  # 沿 first-parent 回溯：保留「仍 >= target 的最小计数」和「< target 的最大计数」两个候选
  cur=$cut; cur_count=$cut_count
  prev_count=-1
  steps=0
  while :; do
    p=$(git -C "$dir" rev-parse --verify --quiet "$cur^1") || break
    pc=$(git -C "$dir" rev-list --count "$p")
    steps=$((steps+1))
    if (( pc >= target )); then
      cur=$p; cur_count=$pc
      (( steps > 200 )) && break          # 防御：正常只需几十步
    else
      prev_count=$pc; prev_sha=$p
      break
    fi
  done

  if (( cur_count == target )); then
    sha=$cur; cnt=$cur_count; kind=exact
  elif (( prev_count >= 0 )) && (( target - prev_count < cur_count - target )); then
    sha=$prev_sha; cnt=$prev_count; kind=near
  else
    sha=$cur; cnt=$cur_count; kind=near
  fi

  d=$(( cnt - target ))
  echo "[ok] $app  ${sha:0:12}  count=$cnt (论文 $target, $(printf '%+d' $d))  $kind  [从 ${cut:0:8} 回溯 $steps 步]"
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%+d\t%s\n" \
    "$app" "${cut:0:12}" "$cut_count" "${sha:0:12}" "$cnt" "$target" "$d" "$kind" >> "$OUT"

  # 把 HEAD 也钉住。这一步很关键：treeless 克隆（--no-checkout）虽然没工作区，
  # 但 HEAD 仍指向默认分支 master 的最新提交（2026 年的代码！）。
  # 不去动它的话，任何人 `git -C repos/kubernetes rev-parse HEAD` 看到的都是现代版本，
  # `rev-list --count HEAD` 会返回 142542 而不是 65684。
  # update-ref 只改 HEAD 引用、不碰索引与工作区，所以不会触发 blob 下载。
  if [[ "$(git -C "$dir" rev-parse HEAD)" != "$sha" ]]; then
    git -C "$dir" update-ref --no-deref HEAD "$sha" \
      && echo "     ↳ HEAD 已游离到 ${sha:0:12}"
  fi
done

echo
column -t -s $'\t' "$OUT" 2>/dev/null || cat "$OUT"
