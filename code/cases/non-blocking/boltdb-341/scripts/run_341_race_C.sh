#!/usr/bin/env bash
# boltdb#341 探针 C：Close 之后继续 Commit（真正会撞 munmap 的路径）
# 依据：bolt 的 Put 写的是 tx 内部 node，只有 Commit 才落 mmap，
#       所以"Close 与 Put 并发"（探针 B）不触雷；必须 Commit。
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
PC="$GOPATH/src/bprobeC"; mkdir -p "$PC"
CSV="$OUT/boltdb341C.csv"
echo "side,probe,run,race,sigsegv,verdict" > "$CSV"

cat > "$PC/main.go" <<'GO'
package main

import (
	"fmt"
	"os"
	"time"

	"github.com/boltdb/bolt"
)

func main() {
	tag := os.Args[1]
	path := "/tmp/b341C_" + tag + ".db"
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
	b.Put([]byte("k1"), []byte("v1"))

	closed := make(chan struct{})
	go func() {
		time.Sleep(100 * time.Millisecond)
		db.Close() // buggy: 不等事务；fixed: 阻塞到事务结束
		close(closed)
	}()

	time.Sleep(200 * time.Millisecond)
	fmt.Println("VERDICT=COMMITTING")
	if err := tx.Commit(); err != nil {
		fmt.Println("VERDICT=COMMIT_ERR:", err)
	} else {
		fmt.Println("VERDICT=COMMIT_OK")
	}
	select {
	case <-closed:
		fmt.Println("VERDICT=CLOSE_DONE")
	case <-time.After(2 * time.Second):
		fmt.Println("VERDICT=CLOSE_PENDING")
	}
}
GO

checkout() {
  git -C "$BOLT" clean -qfd -- functional_test.go 2>/dev/null || true
  git -C "$BOLT" checkout -q -f --detach "$1" || { echo "checkout $1 FAILED"; exit 1; }
  rm -rf "$GOPATH/pkg"
}

run_side() {
  side="$1"; rev="$2"
  checkout "$rev"
  bin="$OUT/bin_C_${side}"
  if ! ( cd "$PC" && "$GO110" build -race -o "$bin" main.go ) > "$OUT/logs/build_C_${side}.log" 2>&1; then
    echo "  BUILD FAILED — see logs/build_C_${side}.log"; head -5 "$OUT/logs/build_C_${side}.log"
    return
  fi
  i=0
  while [ $i -lt "$RUNS" ]; do
    i=$((i+1))
    log="$OUT/logs/C_${side}_run$i.log"
    timeout 60 "$bin" "${side}${i}" > "$log" 2>&1
    rc=$?
    grep -q "WARNING: DATA RACE" "$log" && race=1 || race=0
    grep -q -e "SIGSEGV" -e "segmentation fault" -e "unexpected fault address" "$log" && seg=1 || seg=0
    verdict=$(grep -E "^VERDICT=" "$log" | tr '\n' ' ' | cut -c1-90)
    echo "$side,C,$i,$race,$seg,\"$verdict\"" >> "$CSV"
    printf '  %-5s C run%s  race=%s sigsegv=%s rc=%s  %s\n' "$side" "$i" "$race" "$seg" "$rc" "$verdict"
    sleep 1
  done
}

run_side buggy 55af28c
run_side fixed c69cb102
echo "CSV: $CSV"
