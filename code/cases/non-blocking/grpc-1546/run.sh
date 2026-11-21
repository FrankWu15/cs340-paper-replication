#!/usr/bin/env bash
# grpc#1546 —— 并发 WriteStatus 向已关闭的 writes 通道发送
# 判定：buggy FAIL(panic) ×N，fixed PASS ×N
#
# 与 p4_case.sh 的差别有两处：
#   1) 竞争窗口窄，每轮用 -count=200 重复同一测试；p4_case.sh 固定 -count=1
#   2) 源码按提交号下载并核验 sha256，不依赖本机残留目录
#
# 用法: ./run.sh [count] [iters] [timeout_s]       默认 200 3 120
#   GRPC1546_BUGGY / GRPC1546_FIXED  源码目录，默认 $HOME/grpc1546/{buggy,fixed}
#   GRPC1546_LOGDIR                  输出目录，默认本目录 logs/
#   GRPC1546_REBUILD=1               目录内容与提交不符时强制重下
#   GO1546                           go 可执行文件
#
# 退出码: 0 对照成立  2 buggy 未复现  3 fixed 未全通过  4 源码/构建/环境问题
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUGGY="${GRPC1546_BUGGY:-$HOME/grpc1546/buggy}"
FIXED="${GRPC1546_FIXED:-$HOME/grpc1546/fixed}"
GOBIN="${GO1546:-/usr/local/go-versions/go1.22.9/bin/go}"
COUNT="${1:-200}"
ITERS="${2:-3}"
TMO="${3:-120}"
OUT="${GRPC1546_LOGDIR:-$HERE/logs}"
BUG_SHA=cf79c849790fd644fab2ef0996e07c177f7b689c
FIX_SHA=22c3f92f5faea8db492fb0f5ae4daf0d2752b19e
TEST_RE='TestHandlerTransport_HandleStreams_MultiWriteStatus$'
# 官方树的产品文件与测试文件哈希，用于证明工作目录里的源码就是这两个提交
H_BUG=221095b5340a5a222b135d6dd7b6d1829b495f7ac344b3859f765e47671a94ee
H_FIX=e31892c63815574b668597cbbea2f623bc3f9a70256dff0b600e6a55ed2b663e
H_TEST=efa63412682bbdda47677d07faaed9a1a13aea4d18f9bb63904ede8adf6ec6f8

export GO111MODULE=on
export GOFLAGS=-mod=mod
export GOSUMDB=off
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
# 显式钉住模块缓存：本机 go env 里残留过 GOPATH=/root/go，普通用户下不可写
export GOPATH="${GOPATH:-$HOME/go}"
export GOMODCACHE="${GOMODCACHE:-$HOME/go/pkg/mod}"

fetch_src() {  # $1=目标目录 $2=提交号
  local dir="$1" sha="$2" tmp rc
  tmp=$(mktemp -d) || return 1
  echo "  下载 $sha ..."
  if ! curl -fsSL --max-time 300 \
      "https://codeload.github.com/grpc/grpc-go/tar.gz/$sha" -o "$tmp/src.tgz"; then
    rm -rf "$tmp"
    echo "  下载失败：需要在能访问 GitHub 的环境，或手工准备源码后用 GRPC1546_BUGGY/FIXED 指定"
    return 1
  fi
  mkdir -p "$dir" && tar xzf "$tmp/src.tgz" -C "$dir" --strip-components=1
  rc=$?
  rm -rf "$tmp"
  [ "$rc" -eq 0 ] || return 1
  echo "$sha" > "$dir/.src_sha"
}

prepare() {  # $1=目录 $2=标签 $3=提交号 $4=产品文件期望哈希
  local dir="$1" label="$2" sha="$3" want="$4" actual f

  # 目录内容与提交一致但没记来源时补记，避免为了一个标记重下几十 MB
  if [ ! -f "$dir/.src_sha" ] && [ -f "$dir/transport/handler_server.go" ]; then
    actual=$(sha256sum "$dir/transport/handler_server.go" | cut -d' ' -f1)
    [ "$actual" = "$want" ] && echo "$sha" > "$dir/.src_sha"
  fi

  if [ ! -f "$dir/transport/handler_server.go" ] || \
     [ "$(cat "$dir/.src_sha" 2>/dev/null)" != "$sha" ]; then
    if [ -e "$dir" ] && [ "${GRPC1546_REBUILD:-0}" != "1" ]; then
      echo "[$label] $dir 不是 $sha 的源码树；确认后可加 GRPC1546_REBUILD=1 重下"
      return 1
    fi
    rm -rf "$dir"
    fetch_src "$dir" "$sha" || return 1
  fi

  actual=$(sha256sum "$dir/transport/handler_server.go" | cut -d' ' -f1)
  [ "$actual" = "$want" ] || {
    echo "[$label] handler_server.go 与 $sha 不符：$actual"; return 1; }

  # 依赖文件：缺了补；内容不同则拒绝；相同则统一成 notes/ 的版本（顺带规范行尾）
  for f in go.mod go.sum; do
    if [ ! -f "$dir/$f" ]; then
      cp "$HERE/notes/$f" "$dir/$f"
    elif ! diff -q <(tr -d '\r' < "$HERE/notes/$f") <(tr -d '\r' < "$dir/$f") >/dev/null; then
      if [ "${GRPC1546_REBUILD:-0}" = "1" ]; then
        cp "$HERE/notes/$f" "$dir/$f"
      else
        echo "[$label] $f 与 notes/$f 内容不一致；加 GRPC1546_REBUILD=1 覆盖"; return 1
      fi
    else
      cp "$HERE/notes/$f" "$dir/$f"
    fi
  done

  # 缺陷版没有回归测试，只补测试文件，产品代码保持缺陷
  if ! grep -q 'MultiWriteStatus' "$dir/transport/handler_server_test.go"; then
    ( cd "$dir" && patch -p1 -s < "$HERE/patches/1546-test.patch" ) || {
      echo "[$label] 测试补丁应用失败"; return 1; }
    echo "  [$label] 测试补丁已应用"
  fi

  actual=$(sha256sum "$dir/transport/handler_server_test.go" | cut -d' ' -f1)
  [ "$actual" = "$H_TEST" ] || {
    echo "[$label] 测试文件与官方版本不符：$actual"; return 1; }
  echo "  [$label] 源码核验通过：$(cat "$dir/.src_sha")"
}

write_env() {
  {
    echo "bug=grpc1546"
    echo "sha=$FIX_SHA"
    echo "buggy_sha=$(cat "$BUGGY/.src_sha")"
    echo "fixed_sha=$(cat "$FIXED/.src_sha")"
    echo "test=$TEST_RE"
    echo "pkg=transport"
    echo "count=$COUNT"
    echo "iters=$ITERS"
    echo "timeout=$TMO"
    echo "date=$(date -Is)"
    echo "goroot=$(dirname "$(dirname "$GOBIN")")"
    "$GOBIN" version
    echo "uname=$(uname -sr) $(uname -m)"
    sha256sum "$BUGGY/transport/handler_server.go" "$BUGGY/transport/handler_server_test.go" \
              "$FIXED/transport/handler_server.go" "$FIXED/transport/handler_server_test.go" \
              "$BUGGY/go.mod" "$BUGGY/go.sum" "$FIXED/go.mod" "$FIXED/go.sum"
  } > "$OUT/env.txt"
}

run_side() {  # $1=buggy|fixed  $2=源码目录
  local side="$1" dir="$2" i log rc runs verdict
  local pass=0 fail=0 tmo=0 norun=0 build=0 other=0
  cd "$dir" || return 1
  for i in $(seq 1 "$ITERS"); do
    log="$OUT/grpc_${side}_iter${i}.log"
    timeout $(( TMO * 3 + 90 )) "$GOBIN" test ./transport \
      -run "$TEST_RE" -count="$COUNT" -vet=off -timeout "${TMO}s" -v > "$log" 2>&1
    rc=$?
    runs=$(grep -c '^=== RUN' "$log")
    if grep -q '\[build failed\]' "$log"; then verdict=BUILD_ERROR; build=$((build+1))
    elif grep -q 'no tests to run' "$log"; then verdict=NOTRUN; norun=$((norun+1))
    elif grep -q 'test timed out' "$log"; then verdict=TIMEOUT; tmo=$((tmo+1))
    elif grep -q 'panic: send on closed channel' "$log" && \
         grep -q 'serverHandlerTransport)\.do' "$log"; then
      verdict='FAIL(panic)'; fail=$((fail+1))
    elif [ "$rc" -eq 0 ]; then verdict=PASS; pass=$((pass+1))
    else verdict='FAIL(other)'; other=$((other+1)); fi
    echo "  [$side] iter$i: $verdict  rc=$rc runs=$runs"
  done
  cp "$OUT/grpc_${side}_iter${ITERS}.log" "$OUT/grpc_${side}_last.log"
  echo "  [$side] SUMMARY pass=$pass fail=$fail timeout=$tmo notrun=$norun build=$build other=$other"
  case "$side" in
    buggy) BUG_FAIL=$fail; BUG_BAD=$((tmo + norun + build + other)) ;;
    fixed) FIX_PASS=$pass; FIX_BAD=$((fail + tmo + norun + build + other)) ;;
  esac
}

BUG_FAIL=0; BUG_BAD=0; FIX_PASS=0; FIX_BAD=0

main() {
  [ -x "$GOBIN" ] || { echo "找不到 go: $GOBIN（用 GO1546 指定）"; return 4; }

  echo "############ grpc  fix=$FIX_SHA  pkg=transport  test=$TEST_RE  count=$COUNT  iters=$ITERS  timeout=${TMO}s"
  prepare "$BUGGY" buggy "$BUG_SHA" "$H_BUG" || return 4
  prepare "$FIXED" fixed "$FIX_SHA" "$H_FIX" || return 4
  if ! cmp -s "$BUGGY/transport/handler_server_test.go" "$FIXED/transport/handler_server_test.go"; then
    echo "两侧测试文件不一致，对照不成立"; return 4
  fi
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
  echo "  [grpc] $result  buggy_panic=$BUG_FAIL/$ITERS  fixed_pass=$FIX_PASS/$ITERS"
  echo "############ RESULT: $result"
  echo "############ DONE grpc"
  return "$rc"
}

# 目录必须在起管道前建好：tee 与 main 并行启动，等 main 建目录已经晚了
mkdir -p "$OUT" || { echo "无法创建日志目录: $OUT"; exit 4; }

main 2>&1 | tee "$OUT/summary.txt"
# PIPESTATUS 读取一次就会被下一条命令覆盖，先整体拷出来
rcs=("${PIPESTATUS[@]}")
rc=${rcs[0]}
tee_rc=${rcs[1]:-0}
if [ "$tee_rc" -ne 0 ]; then
  echo "写 $OUT/summary.txt 失败，本次记录不完整（main 退出码 $rc）" >&2
  exit 4
fi
exit "$rc"
