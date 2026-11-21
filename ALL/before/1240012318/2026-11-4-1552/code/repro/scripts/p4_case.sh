#!/usr/bin/env bash
# p4_case.sh —— 单条 bug 的「buggy / fixed」对照复现
#
# 用法: p4_case.sh <repo_dir> <fix_sha> <test_regex> <pkg_subdir> [iters] [timeout_s]
#   repo_dir   : 仓库绝对路径（需在 $GOPATH/src 下）
#   fix_sha    : 修复提交（buggy 取它的第一父提交 ^1）
#   test_regex : go test -run 的正则，用 ^Name$ 精确匹配
#   pkg_subdir : 测试包相对仓库根的路径，根目录填 .
#   iters      : 重复次数（默认 3，课程要求 ≥3 次）
#   timeout_s  : 单次 go test 的 -timeout（默认 30）
#
# 判定口径：输出含 "test timed out" → TIMEOUT（blocking 类 bug 的典型表现）；
#           以 ok 开头 → PASS；以 FAIL 开头 → FAIL；其余 → ERROR（编译失败等）
#
# 测试从修复提交里取：只应用补丁中 *_test.go 的部分，非测试代码保持 buggy。

set -u

REPO=${1:?repo}
FIX=${2:?fix_sha}
REGEX=${3:?test_regex}
PKG=${4:-.}
ITERS=${5:-3}
TMO=${6:-30}

export GOPATH=$HOME/gopath
export GO111MODULE=off
# GOROOT 必须显式钉住：交互式 shell 里可能已设 GOROOT=/usr/local/go(1.27)，
# 那样 go1.10.8 的二进制会用新版标准库，报 internal/goarch 之类的怪错。
export GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH
export GOCACHE=/tmp/gocache_p4

case "$REPO" in
  *google.golang.org/grpc*) TAG=grpc ;;
  *coreos/etcd*)            TAG=etcd ;;
  *docker/docker*)          TAG=docker ;;
  *boltdb/bolt*)            TAG=boltdb ;;
  *)                        TAG=repo ;;
esac

run_label() {   # $1=buggy|fixed
  local label=$1 side
  if [ "$label" = "buggy" ]; then side="$FIX^1"; else side="$FIX"; fi

  cd "$REPO" || return 1
  git checkout -q -f --detach "$side" || { echo "  [$label] CHECKOUT_FAIL $side"; return 1; }
  git clean -qfd

  # buggy 侧没有测试，从修复提交里补上（只取测试文件）
  if [ "$label" = "buggy" ]; then
    git diff "$FIX^1" "$FIX" -- '*_test.go' > /tmp/${TAG}_test.patch 2>/dev/null
    if [ -s /tmp/${TAG}_test.patch ]; then
      if git apply --check /tmp/${TAG}_test.patch 2>/dev/null; then
        git apply /tmp/${TAG}_test.patch && echo "  [$label] 测试补丁已应用"
      elif git apply --3way /tmp/${TAG}_test.patch 2>/dev/null; then
        echo "  [$label] 测试补丁已三方合并"
      else
        echo "  [$label] PATCH_WARN 测试补丁无法应用"
      fi
    else
      echo "  [$label] NO_TEST_PATCH 补丁未包含测试文件"
    fi
  fi

  local i out verdict pass=0 fail=0 tmo=0 err=0 norun=0
  for i in $(seq 1 "$ITERS"); do
    out=$( cd "$REPO/$PKG" && timeout $((TMO * 3 + 90)) go test -vet=off -v -run "$REGEX" -count=1 -timeout "${TMO}s" 2>&1 )
    printf '%s\n' "$out" > "/tmp/${TAG}_${label}_iter${i}.log"
    # 注意：go test 在 -run 没匹配到任何测试时仍输出 ok，必须靠 "no tests to run" 拦下
    if printf '%s' "$out" | grep -q "no tests to run"; then verdict=NOTRUN; norun=$((norun+1))
    elif printf '%s' "$out" | grep -q "test timed out"; then verdict=TIMEOUT; tmo=$((tmo+1))
    elif printf '%s' "$out" | grep -qE '^ok[[:space:]]' && printf '%s' "$out" | grep -q "^=== RUN"; then verdict=PASS; pass=$((pass+1))
    elif printf '%s' "$out" | grep -qE '^(FAIL|---[[:space:]]FAIL)'; then verdict=FAIL; fail=$((fail+1))
    else verdict=ERROR; err=$((err+1)); fi
    echo "  [$label] iter$i: $verdict"
  done

  echo "  [$label] SUMMARY pass=$pass fail=$fail timeout=$tmo notrun=$norun error=$err"
  # 最后一次的输出另存一份便于看现场
  cp "/tmp/${TAG}_${label}_iter${ITERS}.log" "/tmp/${TAG}_${label}_last.log"
}

echo "############ $TAG  fix=$FIX  pkg=$PKG  test=$REGEX  iters=$ITERS  timeout=${TMO}s"
run_label buggy
run_label fixed
echo "############ DONE $TAG"
