#!/usr/bin/env bash
# p4_probe.sh —— 带自写探针的「buggy / fixed」对照复现
#
# 与 p4_case.sh 的区别：B 档 bug 的补丁里没有测试，判定程序要自己写。
# 探针以 *_test.go 的形式注入到被测包目录，两侧都注入（只换被测的源码）。
#
# 用法: p4_probe.sh <repo_dir> <fix_sha> <pkg_subdir> <test_regex> <probe_dir> [iters] [timeout_s] [norace|race]
#   repo_dir   : 仓库绝对路径（需在 $GOPATH/src 下）
#   fix_sha    : 修复提交；buggy 侧取 ^1
#   pkg_subdir : 包相对仓库根的路径，根目录填 .
#   test_regex : go test -run 的正则，用 ^Name$ 精确匹配
#   probe_dir  : 探针目录，其中的 *.go 会被复制进 $repo/$pkg_subdir
#   iters      : 重复次数（默认 3）
#   timeout_s  : 单次 go test 的 -timeout（默认 30）
#   race       : 传 race 则加 -race（数据竞态类 bug）
#
# 判定口径：
#   输出含 "WARNING: DATA RACE"  → RACE    （race 类 bug 已触发）
#   输出含 "test timed out"      → TIMEOUT （blocking 类 bug 已触发）
#   以 ok 开头且出现过 === RUN    → PASS
#   以 FAIL 开头                 → FAIL
#   含 "no tests to run"         → NOTRUN （探针没被编进包，结果无效）
#   其余                         → ERROR  （编译失败、进程崩溃等）

set -u

REPO=${1:?repo}
FIX=${2:?fix_sha}
PKG=${3:-.}
REGEX=${4:?test_regex}
PROBE=${5:?probe_dir}
ITERS=${6:-3}
TMO=${7:-30}
RACEFLAG=${8:-norace}

export GOPATH=$HOME/gopath
export GO111MODULE=off
export GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH
export GOCACHE=/tmp/gocache_p4

TAG=grpc
RACEFLAG_GO=""
[ "$RACEFLAG" = "race" ] && RACEFLAG_GO="-race"

run_label() {
  local label=$1 side
  if [ "$label" = "buggy" ]; then side="$FIX^1"; else side="$FIX"; fi

  cd "$REPO" || return 1
  git checkout -q -f --detach "$side" || { echo "  [$label] CHECKOUT_FAIL $side"; return 1; }
  git clean -qfd

  # 探针必须两侧一致，只复制 *_test.go
  cp "$PROBE"/*_test.go "$REPO/$PKG"/ || { echo "  [$label] PROBE_COPY_FAIL"; return 1; }
  echo "  [$label] 探针已注入: $(cd "$PROBE" && ls *_test.go | tr '\n' ' ')"

  local i out verdict pass=0 fail=0 tmo=0 err=0 norun=0 race=0
  for i in $(seq 1 "$ITERS"); do
    out=$( cd "$REPO/$PKG" && timeout $((TMO * 3 + 120)) go test $RACEFLAG_GO -vet=off -v -run "$REGEX" -count=1 -timeout "${TMO}s" 2>&1 )
    printf '%s\n' "$out" > "/tmp/${TAG}_${label}_iter${i}.log"
    if printf '%s' "$out" | grep -q "no tests to run"; then verdict=NOTRUN; norun=$((norun+1))
    elif printf '%s' "$out" | grep -qE "WARNING: DATA RACE|fatal error: concurrent map"; then verdict=RACE; race=$((race+1))
    elif printf '%s' "$out" | grep -q "test timed out"; then verdict=TIMEOUT; tmo=$((tmo+1))
    elif printf '%s' "$out" | grep -qE '^ok[[:space:]]' && printf '%s' "$out" | grep -q "^=== RUN"; then verdict=PASS; pass=$((pass+1))
    elif printf '%s' "$out" | grep -qE '^(FAIL|---[[:space:]]FAIL)'; then verdict=FAIL; fail=$((fail+1))
    else verdict=ERROR; err=$((err+1)); fi
    echo "  [$label] iter$i: $verdict"
  done

  echo "  [$label] SUMMARY pass=$pass fail=$fail timeout=$tmo race=$race notrun=$norun error=$err"
  cp "/tmp/${TAG}_${label}_iter${ITERS}.log" "/tmp/${TAG}_${label}_last.log"
}

echo "############ $TAG  fix=$FIX  pkg=$PKG  test=$REGEX  probe=$(basename "$PROBE")  race=$RACEFLAG  iters=$ITERS  timeout=${TMO}s"
run_label buggy
run_label fixed
echo "############ DONE $TAG"
