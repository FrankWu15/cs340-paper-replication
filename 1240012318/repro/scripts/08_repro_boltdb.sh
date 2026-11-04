#!/usr/bin/env bash
# 08_repro_boltdb.sh — 复现 boltdb 两条 artifact 标记"已复现"的 bug
#
# 必须在 Linux 上执行（Ubuntu 18.04 + Go 1.10.8 + GOPATH 布局）。
# 论文用 GOPATH 模式（无 go.mod），Go 1.10.8 最接近论文环境。
#
# 用法：
#   GOPATH=$HOME/gopath ./08_repro_boltdb.sh
#   OUT=$HOME/repro-out ./08_repro_boltdb.sh
#
# 判定标准（对应论文 §4 "leveraged the symptom mentioned in the bug report"）：
#   boltdb#341   符号：Close 在事务未结束时提前返回       → VERDICT=BUG
#   boltdb@7fb06 符号：并发读写导致 panic / 元数据撕裂    → VERDICT=BUG
#
# 关键前置（踩过的坑，勿删）：
#   1. 每次 checkout 后必须 rm -rf $GOPATH/pkg，否则外部测试包会链接旧编译产物
#   2. boltdb#341 的官方测试无效：它调用 TestDB.Close()，内部 MustCheck()
#      会开写事务阻塞在 rwlock 上，bolt.DB.Close() 从未被执行。必须用独立探针。

set -u

GOPATH=${GOPATH:-$HOME/gopath}
export GOPATH          # 必须 export：否则 go 子进程回落到默认 $HOME/go
GO=${GO:-/usr/local/go1.10.8/bin/go}
GO110=${GO110:-/usr/local/go1.10.8/bin/go}
BOLT=$GOPATH/src/github.com/boltdb/bolt
OUT=${OUT:-$HOME/repro-out}
PROBE_DIR=$GOPATH/src/boltprobe

export GO111MODULE=off
export PATH=$(dirname "$GO110"):$PATH
mkdir -p "$OUT" "$PROBE_DIR"

log() { printf '%s\n' "$*"; }

fail() { log "[!] $*"; exit 1; }

require_env() {
  [ -d "$BOLT/.git" ] || fail "找不到 $BOLT，请先同步 boltdb 仓库到 GOPATH"
  [ -x "$GO110" ] || fail "找不到 $GO110"
  "$GO110" version | grep -q go1.10 || fail "该实验需 Go 1.10.x"
  # 第二条要编译 testdata，需要 testify（报错时提示如何准备）
  if [ ! -d "$GOPATH/src/github.com/stretchr/testify/assert" ]; then
    fail "缺少 testify：git clone -b v1.2.2 https://github.com/stretchr/testify $GOPATH/src/github.com/stretchr/testify"
  fi
}

clean_cache() {
  # GOPATH 模式下 pkg/ 里的 .a 不会因 git checkout 自动失效，
  # 会导致外部测试包链接到上一个版本的代码。
  rm -rf "$GOPATH/pkg"
}

checkout() {
  local rev=$1
  # functional_test.go 在旧版本里是「新增的未跟踪文件」，切换前必须清掉，
  # 否则 git 会拒绝覆盖（untracked working tree file would be overwritten）。
  git -C "$BOLT" clean -qfd -- functional_test.go 2>/dev/null || true
  git -C "$BOLT" checkout -q -f --detach "$rev" || fail "checkout $rev 失败"
  clean_cache
}

# ---------------------------------------------------------------- boltdb#341
# 症状：DB.Close() 不与未完成的事务同步，close() 里 munmap 后，
#       事务 Commit 访问 DB.page() 得到 nil → SIGSEGV。
# 修复 c69cb102：Close() 增加 db.rwlock.Lock() + db.mmaplock.RLock()
repro_341() {
  local buggy=55af28c fixed=c69cb102
  cat > "$PROBE_DIR/main.go" <<'GO'
package main

import (
	"fmt"
	"os"
	"sync/atomic"
	"time"

	"github.com/boltdb/bolt"
)

func run(tag string) {
	path := "/tmp/bolt341_" + tag + ".db"
	os.Remove(path)
	db, err := bolt.Open(path, 0666, nil)
	if err != nil {
		fmt.Println("VERDICT=ERROR open:", err)
		return
	}
	tx, err := db.Begin(true)
	if err != nil {
		fmt.Println("VERDICT=ERROR begin:", err)
		return
	}

	var closeMs int64 = -1
	done := make(chan struct{})
	go func() {
		t0 := time.Now()
		db.Close()
		atomic.StoreInt64(&closeMs, int64(time.Since(t0)/time.Millisecond))
		close(done)
	}()

	time.Sleep(150 * time.Millisecond)
	early := false
	select {
	case <-done:
		early = true
	default:
	}
	if early {
		fmt.Printf("VERDICT=BUG close_returned_early closeMs=%d\n", atomic.LoadInt64(&closeMs))
		// 不 Commit：已知会 SIGSEGV，那是附加证据而非判据
		return
	}
	tx.Commit()
	<-done
	fmt.Printf("VERDICT=OK close_waited closeMs=%d\n", atomic.LoadInt64(&closeMs))
}

func main() {
	run(os.Args[1])
}
GO

  local rc=0
  local buggy_full fixed_full
  checkout "$buggy"
  local buggy_out
  buggy_full=$("$GO110" run "$PROBE_DIR/main.go" buggy 2>&1)
  printf '%s\n' "$buggy_full" > "$OUT/boltdb_341_buggy.log"
  buggy_out=$(printf '%s\n' "$buggy_full" | grep -E '^VERDICT=' | tail -1)
  log "  buggy  $buggy → ${buggy_out:-<no output>}"
  case "$buggy_out" in
    VERDICT=BUG*) : ;;
    *) rc=1 ;;
  esac

  checkout "$fixed"
  local fixed_out
  fixed_full=$("$GO110" run "$PROBE_DIR/main.go" fixed 2>&1)
  printf '%s\n' "$fixed_full" > "$OUT/boltdb_341_fixed.log"
  fixed_out=$(printf '%s\n' "$fixed_full" | grep -E '^VERDICT=' | tail -1)
  log "  fixed  $fixed   → ${fixed_out:-<no output>}"
  case "$fixed_out" in
    VERDICT=OK*) : ;;
    *) rc=1 ;;
  esac

  if [ $rc -eq 0 ]; then
    log "[REPRODUCED] boltdb#341  症状：Close 提前返回，事务提交时访问已 unmap 内存"
  else
    log "[INCONCLUSIVE] boltdb#341  对照不成立，检查环境"
  fi
  return $rc
}

# ------------------------------------------------------------ boltdb@7fb06fee
# 症状：读事务直接引用 db.meta（共享），写事务修改 meta.txnid 时发生竞争，
#       并发读写会读到撕裂的页面 → panic: invalid page type: meta / 断言失败
# 修复 7fb06fee：Transaction.init 改为复制 meta（每个事务持有独立副本）
#
# 该测试本身不稳定（多 goroutine 并发调用 t.FailNow()，且 `local := current`
# 只是浅拷贝 slice header），fixed 版本也会偶发失败。因此按论文 §4
# 「run a buggy program a lot of times」的做法，统计 N 次的失败构成，
# 而不是单次 PASS/FAIL。
REPRO_ITERS=${REPRO_ITERS:-10}
repro_7fb06() {
  local buggy=7fb06fee^ fixed=7fb06fee
  local iters=$REPRO_ITERS

  run_batch() {
    local tag=$1 rev=$2
    checkout "$rev"
    if [ "$rev" = "$buggy" ]; then
      git -C "$BOLT" show "$fixed:functional_test.go" > "$BOLT/functional_test.go" \
        || fail "取出 functional_test.go 失败"
      git -C "$BOLT" show "$fixed:db_test.go" > "$BOLT/db_test.go" \
        || fail "取出 db_test.go 失败"
    fi
    local pass=0 panic=0 other=0 i out
    for i in $(seq 1 "$iters"); do
      out=$( cd "$BOLT" && timeout 180 "$GO110" test -race -count=1 -run Parallel 2>&1 )
      if printf '%s' "$out" | grep -q "invalid page type"; then
        panic=$((panic+1))
      elif printf '%s' "$out" | grep -q '^FAIL'; then
        other=$((other+1))
      else
        pass=$((pass+1))
      fi
    done
    printf '%s' "$out" > "$OUT/boltdb_7fb06_${tag}_last.log"
    printf '%s|%s|%s' "$pass" "$panic" "$other"
  }

  local buggy_res fixed_res
  buggy_res=$(run_batch buggy "$buggy")
  fixed_res=$(run_batch fixed "$fixed")

  IFS='|' read -r b_pass b_panic b_other <<< "$buggy_res"
  IFS='|' read -r f_pass f_panic f_other <<< "$fixed_res"

  log "  buggy  7fb06fee^ → PASS=$b_pass/$iters panic(invalid_page)=$b_panic other_FAIL=$b_other"
  log "  fixed  7fb06fee  → PASS=$f_pass/$iters panic(invalid_page)=$f_panic other_FAIL=$f_other"

  # 判据：buggy 出现元数据撕裂且 fixed 不出现；同时 buggy 失败率显著更高
  local rc=0
  if [ "$b_panic" -eq 0 ]; then
    log "  [!] buggy 未观察到 invalid page type，可能需增加迭代次数"
    rc=1
  fi
  if [ "$f_panic" -ne 0 ]; then
    log "  [!] fixed 也出现元数据撕裂，修复无效或环境异常"
    rc=1
  fi
  if [ "$b_pass" -gt "$f_pass" ]; then
    log "  [!] buggy 通过次数多于 fixed，判定异常"
    rc=1
  fi

  if [ $rc -eq 0 ]; then
    log "[REPRODUCED] boltdb@7fb06fee  症状：并发读写元数据撕裂（invalid page type: meta）"
    log "   buggy 失败率 $(( (b_panic + b_other) * 100 / iters ))% vs fixed $(( (f_panic + f_other) * 100 / iters ))%，$iters 次统计"
  else
    log "[INCONCLUSIVE] boltdb@7fb06fee  统计不成立，检查环境或加大 REPRO_ITERS"
  fi
  return $rc
}

main() {
  require_env
  log "== boltdb 两条目标 bug 复现 =="
  log "GOPATH=$GOPATH  GO=$($GO110 version)  OUT=$OUT"
  log ""
  local bad=0
  log "-- boltdb#341 (close-race) --"
  repro_341 || bad=$((bad+1))
  log ""
  log "-- boltdb@7fb06fee (parallel-tx) --"
  repro_7fb06 || bad=$((bad+1))
  log ""
  if [ $bad -eq 0 ]; then
    log "RESULT: 2/2 复现成功（buggy 触发、fixed 通过）"
  else
    log "RESULT: $bad/2 未通过，需人工核查"
  fi
  return $bad
}

main "$@"
