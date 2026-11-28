#!/usr/bin/env bash
# boltdb#341 补测：给它补上 -race 证据
# 两个探针，避免"探针写得不并发 → 误判 -race 抓不到"
#   A 原样探针（与已入库判定同一份：buggy 分支提前 return，之后不再碰 db）
#   B 并发探针（写事务在循环 Put 的同时另一路 Close —— 真正让两者并发）
# 判据：进程输出里有 "WARNING: DATA RACE"；副作用记 VERDICT / SIGSEGV
set -u
GOPATH="${REPRO_GOPATH:-$HOME/gopath}"
GO110="${GO110:-/usr/local/go1.10.8/bin/go}"
export GOPATH GO111MODULE=off
export GOROOT="$(dirname "$(dirname "$GO110")")"
export PATH="$GOROOT/bin:$PATH"
export GORACE="halt_on_error=1"
BOLT="$GOPATH/src/github.com/boltdb/bolt"
OUT="$HOME/repro1128/11-28/boltdb341-race"
RUNS="${RUNS:-3}"
mkdir -p "$OUT/logs"
CSV="$OUT/boltdb341.csv"
echo "side,probe,run,race,sigsegv,verdict" > "$CSV"

checkout() {
  git -C "$BOLT" clean -qfd -- functional_test.go 2>/dev/null || true
  git -C "$BOLT" checkout -q -f --detach "$1" || { echo "checkout $1 FAILED"; exit 1; }
  rm -rf "$GOPATH/pkg"
}

PA="$GOPATH/src/bprobeA"; PB="$GOPATH/src/bprobeB"
mkdir -p "$PA" "$PB"

cat > "$PA/main.go" <<'GO'
package main

import (
	"fmt"
	"os"
	"sync/atomic"
	"time"

	"github.com/boltdb/bolt"
)

func main() {
	tag := os.Args[1]
	path := "/tmp/b341A_" + tag + ".db"
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
	select {
	case <-done:
		fmt.Printf("VERDICT=BUG close_returned_early closeMs=%d\n", atomic.LoadInt64(&closeMs))
		return
	default:
	}
	tx.Commit()
	<-done
	fmt.Printf("VERDICT=OK close_waited closeMs=%d\n", atomic.LoadInt64(&closeMs))
}
GO

cat > "$PB/main.go" <<'GO'
package main

import (
	"fmt"
	"os"
	"time"

	"github.com/boltdb/bolt"
)

func main() {
	tag := os.Args[1]
	path := "/tmp/b341B_" + tag + ".db"
	os.Remove(path)
	db, err := bolt.Open(path, 0666, nil)
	if err != nil {
		fmt.Println("VERDICT=ERROR open:", err)
		return
	}
	if err := db.Update(func(tx *bolt.Tx) error {
		_, e := tx.CreateBucketIfNotExists([]byte("b"))
		return e
	}); err != nil {
		fmt.Println("VERDICT=ERROR setup:", err)
		return
	}
	tx, err := db.Begin(true)
	if err != nil {
		fmt.Println("VERDICT=ERROR begin:", err)
		return
	}
	b := tx.Bucket([]byte("b"))

	// 另一路：100ms 后 Close（buggy 版不会等待写事务）
	go func() {
		time.Sleep(100 * time.Millisecond)
		db.Close()
	}()

	// 主路：持续用这个写事务，Close 与它在时间上重叠
	deadline := time.Now().Add(3 * time.Second)
	n := 0
	for time.Now().Before(deadline) {
		if err := b.Put([]byte("k"), []byte("v")); err != nil {
			fmt.Println("VERDICT=PUT_ERR:", err)
			break
		}
		n++
	}
	fmt.Printf("VERDICT=RAN puts=%d\n", n)
}
GO

run_side() {
  side="$1"; rev="$2"
  checkout "$rev"
  for p in A B; do
    dir="$GOPATH/src/bprobe$p"
    bin="$OUT/bin_${p}_${side}"
    if ! ( cd "$dir" && "$GO110" build -race -o "$bin" main.go ) > "$OUT/logs/build_${p}_${side}.log" 2>&1; then
      echo "  BUILD FAILED ($p/$side) — see logs/build_${p}_${side}.log"
      echo "$side,$p,build_failed,0,0,-" >> "$CSV"
      continue
    fi
    i=0
    while [ $i -lt "$RUNS" ]; do
      i=$((i+1))
      log="$OUT/logs/${p}_${side}_run$i.log"
      timeout 30 "$bin" "${side}${i}" > "$log" 2>&1
      rc=$?
      grep -q "WARNING: DATA RACE" "$log" && race=1 || race=0
      grep -q -e "SIGSEGV" -e "segmentation fault" -e "unexpected fault address" "$log" && seg=1 || seg=0
      verdict=$(grep -E "^VERDICT=" "$log" | tail -1 | cut -c1-60)
      [ -z "$verdict" ] && verdict="(none,rc=$rc)"
      echo "$side,$p,$i,$race,$seg,\"$verdict\"" >> "$CSV"
      printf '  %-5s probe%s run%s  race=%s sigsegv=%s  %s\n' "$side" "$p" "$i" "$race" "$seg" "$verdict"
      sleep 1
    done
  done
}

echo "== env =="
"$GO110" version
git -C "$BOLT" log --oneline -1 2>/dev/null
echo

run_side buggy 55af28c
run_side fixed c69cb102

echo
echo "== 汇总（race=1 的轮次） =="
awk -F, 'NR>1 && $4==1 {c[$1"_"$2]++} END{for(k in c) printf "  %s: %d 轮报 DATA RACE\n", k, c[k]}' "$CSV"
[ "$(awk -F, 'NR>1 && $4==1' "$CSV" | wc -l)" -eq 0 ] && echo "  (无)"
echo "CSV: $CSV"
