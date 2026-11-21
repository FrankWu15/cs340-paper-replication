#!/bin/bash
# P5 单条 blocking bug 的「裸进程」检测：去掉所有 Go 层 timer，让 checkdead 有机会触发。
# usage: run_one.sh <fix_sha> <pkg_subdir> <test_regex> [wait_sec]
set -u
export GOPATH=$HOME/gopath GO111MODULE=off GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH GOCACHE=/tmp/gocache_p4
REPO=$GOPATH/src/google.golang.org/grpc
FIX=$1; PKG=$2; RE=$3; WAIT=${4:-25}
cd "$REPO" || { echo "NO_REPO"; exit 1; }
git checkout -f --detach "${FIX}^" >/dev/null 2>&1 || { echo "CHECKOUT_FAIL"; exit 1; }
git clean -fdq
git diff "${FIX}^" "$FIX" -- '*_test.go' > /tmp/p5/t.patch 2>/dev/null
if [ -s /tmp/p5/t.patch ]; then
  if git apply /tmp/p5/t.patch 2>/dev/null; then echo "test_patch=applied"
  elif git apply --3way /tmp/p5/t.patch 2>/dev/null; then echo "test_patch=3way"
  else echo "test_patch=WARN"; fi
else
  echo "test_patch=none"
fi
cd "$REPO/$PKG" || { echo "NO_PKG"; exit 1; }
go test -vet=off -run "$RE" -count=1 -c -o /tmp/p5/t.bin > /tmp/p5/build.log 2>&1
BRC=$?
echo "build_rc=$BRC"
if [ "$BRC" -ne 0 ]; then tail -6 /tmp/p5/build.log; exit 1; fi
timeout -s QUIT "$WAIT" /tmp/p5/t.bin -test.v -test.timeout 0 -test.run "$RE" > /tmp/p5/run.log 2>&1
RC=$?
echo "run_rc=$RC   (124=被外部杀掉/静默挂起, 2=信号退出)"
echo "deadlock_msg=$(grep -c 'all goroutines are asleep' /tmp/p5/run.log)"
echo "goroutines=$(grep -c '^goroutine ' /tmp/p5/run.log)"
echo "runs=$(grep -c '^=== RUN' /tmp/p5/run.log)"
echo "testtimeout_panic=$(grep -c 'test timed out' /tmp/p5/run.log)"
echo "--- last lines:"
tail -4 /tmp/p5/run.log
