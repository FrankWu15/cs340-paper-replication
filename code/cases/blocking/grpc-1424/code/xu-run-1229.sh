#!/usr/bin/env bash
# grpc#1424 个人复跑入口（Go 1.22.9 + module）
# 与同目录 run.sh 的 Go 1.10.8 + GOPATH 路径相互独立，两条都可单独跑通。
# 判定：buggy FAIL（100ms 内 doneChan 未关闭），fixed PASS
#
# 用法: ./xu-run-1229.sh [iters] [timeout_s]        默认 3 60
#   XU1424_BUGGY / XU1424_FIXED  源码目录，默认 $HOME/grpc1424/{buggy,fixed}
#   XU1424_LOGDIR                输出目录，默认 <case>/logs/xu/1229
#   XU1424_REBUILD=1             目录内容与提交不符时强制重下
#   GO1424                       go 可执行文件
#
# 退出码: 0 对照成立  2 buggy 未复现  3 fixed 未通过  4 源码/构建/环境问题
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="$(dirname "$HERE")"
BUGGY="${XU1424_BUGGY:-$HOME/grpc1424/buggy}"
FIXED="${XU1424_FIXED:-$HOME/grpc1424/fixed}"
GOBIN="${GO1424:-/usr/local/go-versions/go1.22.9/bin/go}"
ITERS="${1:-3}"
TMO="${2:-60}"
OUT="${XU1424_LOGDIR:-$CASE/logs/xu/1229}"
BUG_SHA=39c8c3866d926d95e11c03508bf83d00f2963f91
FIX_SHA=4e56696c6c5a8cd7b711a1eb8936463559361da5
TEST_RE='TestClientLBWatcherWithClosedBalancer$'
# 两个提交下 clientconn.go 的哈希；测试文件在修复提交里新增，两侧一致
H_BUG=c4bd8a8bce34ef57a7895048e7eb31b574c8323f088a60d6bc8ca695c132f301
H_FIX=4a1f8173e9c4b25992ccb9dff1a89460c8f1f0823a590110f613e306fa98a3d1
H_TEST=9df6aea5d8d0244ab83d61884c03cc5991fc08de9772bb3adaf48bc3a05fbec4

export GO111MODULE=on
export GOFLAGS=-mod=mod
export GOSUMDB=off
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
export GOPATH="${GOPATH:-$HOME/go}"
export GOMODCACHE="${GOMODCACHE:-$HOME/go/pkg/mod}"

fetch_src() {  # $1=目录 $2=提交号
  local dir="$1" sha="$2" tmp rc
  tmp=$(mktemp -d) || return 1
  echo "  下载 $sha ..."
  if ! curl -fsSL --max-time 300 \
      "https://codeload.github.com/grpc/grpc-go/tar.gz/$sha" -o "$tmp/src.tgz"; then
    rm -rf "$tmp"
    echo "  下载失败：可在能访问 GitHub 的机器上备份源码，再用 XU1424_BUGGY/FIXED 指定"
    return 1
  fi
  mkdir -p "$dir" && tar xzf "$tmp/src.tgz" -C "$dir" --strip-components=1
  rc=$?
  rm -rf "$tmp"
  [ "$rc" -eq 0 ] || return 1
  echo "$sha" > "$dir/.src_sha"
}

prepare() {  # $1=目录 $2=标签 $3=提交号 $4=clientconn.go 期望哈希
  local dir="$1" label="$2" sha="$3" want="$4" actual f

  if [ ! -f "$dir/.src_sha" ] && [ -f "$dir/clientconn.go" ]; then
    actual=$(sha256sum "$dir/clientconn.go" | cut -d' ' -f1)
    [ "$actual" = "$want" ] && echo "$sha" > "$dir/.src_sha"
  fi
  if [ ! -f "$dir/clientconn.go" ] || [ "$(cat "$dir/.src_sha" 2>/dev/null)" != "$sha" ]; then
    if [ -e "$dir" ] && [ "${XU1424_REBUILD:-0}" != "1" ]; then
      echo "[$label] $dir 不是 $sha 的源码树；确认后可加 XU1424_REBUILD=1 重下"
      return 1
    fi
    rm -rf "$dir"
    fetch_src "$dir" "$sha" || return 1
  fi

  actual=$(sha256sum "$dir/clientconn.go" | cut -d' ' -f1)
  [ "$actual" = "$want" ] || { echo "[$label] clientconn.go 与 $sha 不符：$actual"; return 1; }

  for f in go.mod go.sum; do
    if [ ! -f "$dir/$f" ]; then
      cp "$CASE/notes/01-lbwatcher-leak.$f" "$dir/$f"
    elif ! diff -q <(tr -d '\r' < "$CASE/notes/01-lbwatcher-leak.$f") <(tr -d '\r' < "$dir/$f") >/dev/null; then
      if [ "${XU1424_REBUILD:-0}" = "1" ]; then
        cp "$CASE/notes/01-lbwatcher-leak.$f" "$dir/$f"
      else
        echo "[$label] $f 与 notes/01-lbwatcher-leak.$f 内容不一致；加 XU1424_REBUILD=1 覆盖"
        return 1
      fi
    else
      cp "$CASE/notes/01-lbwatcher-leak.$f" "$dir/$f"
    fi
  done
  echo "  [$label] 源码核验通过：$(cat "$dir/.src_sha")"
}

# 缺陷版补测试：修复提交只新增了一个测试函数，两侧 clientconn_test.go 因此完全一致，
# 直接用修复版那份覆盖，等价于只应用测试部分的 diff（产品代码不动）。
inject_test() {
  cp "$FIXED/clientconn_test.go" "$BUGGY/clientconn_test.go" || return 1
  local actual
  actual=$(sha256sum "$BUGGY/clientconn_test.go" | cut -d' ' -f1)
  [ "$actual" = "$H_TEST" ] || { echo "[buggy] 测试文件与官方版本不符：$actual"; return 1; }
  cmp -s "$BUGGY/clientconn_test.go" "$FIXED/clientconn_test.go" || {
    echo "两侧测试文件不一致，对照不成立"; return 1; }
  echo "  [buggy] 测试文件已补齐（与 fixed 一致）"
}

write_env() {
  {
    echo "bug=grpc1424"
    echo "path=go1.22.9-module"
    echo "sha=$FIX_SHA"
    echo "buggy_sha=$(cat "$BUGGY/.src_sha")"
    echo "fixed_sha=$(cat "$FIXED/.src_sha")"
    echo "test=$TEST_RE"
    echo "pkg=."
    echo "iters=$ITERS"
    echo "timeout=$TMO"
    echo "date=$(date -Is)"
    echo "goroot=$(dirname "$(dirname "$GOBIN")")"
    "$GOBIN" version
    echo "uname=$(uname -sr) $(uname -m)"
    sha256sum "$BUGGY/clientconn.go" "$BUGGY/clientconn_test.go" \
              "$FIXED/clientconn.go" "$FIXED/clientconn_test.go" \
              "$BUGGY/go.mod" "$BUGGY/go.sum" "$FIXED/go.mod" "$FIXED/go.sum"
  } > "$OUT/env.txt"
}

run_side() {  # $1=buggy|fixed $2=目录
  local side="$1" dir="$2" i log rc verdict
  local pass=0 fail=0 other=0
  cd "$dir" || return 1
  for i in $(seq 1 "$ITERS"); do
    log="$OUT/grpc_${side}_iter${i}.log"
    timeout $(( TMO * 3 + 60 )) "$GOBIN" test . -run "$TEST_RE" -count=1 -vet=off -timeout "${TMO}s" -v > "$log" 2>&1
    rc=$?
    if grep -q '\[build failed\]' "$log"; then verdict=BUILD_ERROR; other=$((other+1))
    elif grep -q 'test timed out' "$log"; then verdict=TIMEOUT; other=$((other+1))
    elif grep -q "didn't close doneChan" "$log"; then verdict='FAIL(assert)'; fail=$((fail+1))
    elif [ "$rc" -eq 0 ]; then verdict=PASS; pass=$((pass+1))
    else verdict='FAIL(other)'; other=$((other+1)); fi
    echo "  [$side] iter$i: $verdict  rc=$rc"
  done
  cp "$OUT/grpc_${side}_iter${ITERS}.log" "$OUT/grpc_${side}_last.log"
  echo "  [$side] SUMMARY pass=$pass fail=$fail other=$other"
  case "$side" in
    buggy) BUG_FAIL=$fail; BUG_BAD=$other ;;
    fixed) FIX_PASS=$pass; FIX_BAD=$((fail + other)) ;;
  esac
}

BUG_FAIL=0; BUG_BAD=0; FIX_PASS=0; FIX_BAD=0

main() {
  [ -x "$GOBIN" ] || { echo "找不到 go: $GOBIN（用 GO1424 指定）"; return 4; }

  echo "############ grpc1424  path=go1.22.9-module  test=$TEST_RE  iters=$ITERS  timeout=${TMO}s"
  prepare "$FIXED" fixed "$FIX_SHA" "$H_FIX" || return 4
  prepare "$BUGGY" buggy "$BUG_SHA" "$H_BUG" || return 4
  inject_test || return 4
  write_env

  run_side buggy "$BUGGY"
  run_side fixed "$FIXED"

  local result rc
  if [ "$BUG_BAD" -gt 0 ] || [ "$FIX_BAD" -gt 0 ]; then
    result="ENV_ERROR"; rc=4
  elif [ "$BUG_FAIL" -eq 0 ]; then
    result="NOT REPRODUCED"; rc=2
  elif [ "$FIX_PASS" -ne "$ITERS" ]; then
    result="FIXED_NOT_PASS"; rc=3
  else
    result="REPRODUCED"; rc=0
  fi
  echo "  [grpc1424] $result  buggy_fail=$BUG_FAIL/$ITERS  fixed_pass=$FIX_PASS/$ITERS"
  echo "############ RESULT: $result"
  echo "############ DONE grpc1424"
  return "$rc"
}

# 目录先建好：tee 与 main 并行启动，等 main 建目录就晚了
mkdir -p "$OUT" || { echo "无法创建日志目录: $OUT"; exit 4; }

main 2>&1 | tee "$OUT/summary.txt"
rcs=("${PIPESTATUS[@]}")
rc=${rcs[0]}
tee_rc=${rcs[1]:-0}
if [ "$tee_rc" -ne 0 ]; then
  echo "写 $OUT/summary.txt 失败，本次记录不完整（main 退出码 $rc）" >&2
  exit 4
fi
exit "$rc"
