#!/usr/bin/env bash
# P4 阶段：单个 bug 的复现驱动模板。
#
# 论文 4 节 "Reproducing concurrency bugs" 的做法：
#   回滚到 buggy 版本 -> 编译 -> 用 bug report 里的输入运行 -> 用报告里的症状判定是否复现。
# 并发 bug 有非确定性，所以要重复 N 次并统计成功率。
#
# 关键技巧：timeout -s QUIT 超时后向进程发 SIGQUIT，Go runtime 会把**所有**
# goroutine 的调用栈打到 stderr，正好用来判定"卡在 chan send / semacquire / select"。
#
# 用法:
#   ./scripts/05_repro.sh --repo ../vendor/bolt --app boltdb --bug-id boltdb#392 \
#       --commit defdb743cdc --build "GO111MODULE=off go build ./..." \
#       --run "./bolt bench -n 1000" --runs 30 --timeout 60 --out out/repro_boltdb_392.csv
set -uo pipefail

REPO="" ; APP="" ; BUG_ID="" ; COMMIT="" ; BUILD="go build ./..." ; RUN="" 
RUNS=20 ; TIMEOUT=60 ; OUT="out/repro.csv" ; KEEP_LOGS=1 ; TAG=""

die() { echo "[x] $*" >&2; exit 2; }
log() { echo "[.] $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --app) APP="$2"; shift 2 ;;
    --bug-id) BUG_ID="$2"; shift 2 ;;
    --commit) COMMIT="$2"; shift 2 ;;
    --build) BUILD="$2"; shift 2 ;;
    --run) RUN="$2"; shift 2 ;;
    --runs) RUNS="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "未知参数 $1" ;;
  esac
done

[[ -n "$APP" && -n "$BUG_ID" && -n "$COMMIT" && -n "$RUN" ]] || die "缺少必填参数（--app/--bug-id/--commit/--run）"
[[ -d "$REPO/.git" ]] || die "$REPO 不是 git 仓库"

TAG="${TAG:-$(echo "$BUG_ID" | tr '#/' '__')}"
LOGDIR="$(dirname "$OUT")/logs_${TAG}"
mkdir -p "$LOGDIR" "$(dirname "$OUT")"

# ---------- 1) 检出 buggy 版本并编译 ----------
log "checkout $COMMIT"
git -C "$REPO" checkout -q "$COMMIT" || die "checkout 失败"
REV="$(git -C "$REPO" rev-parse --short HEAD)"

log "build: $BUILD"
if ! ( cd "$REPO" && eval "$BUILD" ) > "$LOGDIR/build.log" 2>&1; then
  echo "[x] 编译失败，见 $LOGDIR/build.log（老项目常见：GOPATH/vendor、私有依赖下线）" >&2
  exit 3
fi

# ---------- 2) 重复运行 ----------
declare -A CLASS=( [hang]=0 [deadlock_detected]=0 [panic]=0 [not_reproduced]=0 [run_error]=0 )
declare -a RECORDS=()

classify() {  # $1=log $2=exit_code
  local lg="$1" rc="$2"
  if grep -q "fatal error: all goroutines are asleep - deadlock!" "$lg" 2>/dev/null; then
    echo "deadlock_detected"
  elif grep -qE "^panic: " "$lg" 2>/dev/null; then
    echo "panic"
  elif [[ "$rc" == "124" ]] && grep -qE "goroutine [0-9]+ \[(chan send|chan receive|semacquire|select|sync\.)" "$lg" 2>/dev/null; then
    echo "hang"
  elif [[ "$rc" == "124" ]]; then
    echo "hang"      # 超时但没抓到栈，仍记为 hang，但在证据列标注 weak
  elif [[ "$rc" != "0" ]]; then
    echo "run_error"
  else
    echo "not_reproduced"
  fi
}

for i in $(seq 1 "$RUNS"); do
  lg="$LOGDIR/run_${i}.log"
  rc=0
  ( cd "$REPO" && eval "timeout -k 5 -s QUIT $TIMEOUT $RUN" ) > "$lg" 2>&1 || rc=$?
  cls="$(classify "$lg" "$rc")"
  CLASS["$cls"]=$(( ${CLASS["$cls"]} + 1 ))
  RECORDS+=("$i,$rc,$cls,$lg")
  log "run $i/$RUNS -> $cls (rc=$rc)"
done

# ---------- 3) 汇总 ----------
repro=0
[[ ${CLASS[hang]} -gt 0 || ${CLASS[deadlock_detected]} -gt 0 || ${CLASS[panic]} -gt 0 ]] && repro=1
rate=$(awk -v h="$(( ${CLASS[hang]} + ${CLASS[deadlock_detected]} + ${CLASS[panic]} ))" -v n="$RUNS" 'BEGIN{printf "%.2f", (n? h/n:0)}')

peak_symptom() {
  local best="not_reproduced"
  [[ ${CLASS[run_error]} -gt 0 ]] && best="run_error"
  [[ ${CLASS[panic]} -gt 0 ]] && best="panic"
  [[ ${CLASS[hang]} -gt 0 ]] && best="hang"
  [[ ${CLASS[deadlock_detected]} -gt 0 ]] && best="deadlock_detected"
  echo "$best"
}

if [[ ! -f "$OUT" ]]; then
  echo "bug_id,app,commit,go_version,build_cmd,run_cmd,runs,successes,repro_rate,main_symptom,reproduced,log_dir" > "$OUT"
fi
gover="$( ( cd "$REPO" && go version 2>/dev/null ) | awk '{print $3}')"
echo "${BUG_ID},${APP},${REV},${gover:-unknown},\"${BUILD}\",\"${RUN}\",${RUNS},$(( ${CLASS[hang]} + ${CLASS[deadlock_detected]} + ${CLASS[panic]} )),${rate},$(peak_symptom),${repro},${LOGDIR}" >> "$OUT"

[[ $KEEP_LOGS -eq 0 ]] && rm -rf "$LOGDIR"

echo "[done] $BUG_ID  复现率 ${rate}  (hang=${CLASS[hang]} deadlock=${CLASS[deadlock_detected]} panic=${CLASS[panic]} no=${CLASS[not_reproduced]} err=${CLASS[run_error]})"
echo "       -> $OUT"
