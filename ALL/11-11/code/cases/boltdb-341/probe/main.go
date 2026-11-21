// bolt341 探针 —— 检测 bolt.DB.Close() 是否在写事务未结束时提前返回。
//
// 为什么不用官方测试：bug 修复提交里的 TestDB.Close() 会调用 TestDB.Close()
// （测试自定义方法）而不是 bolt.DB.Close()，被 MustCheck() 里的写事务阻塞，
// 真正被检验的 Close 从未执行，永远 PASS。见 docs/p4-repro-boltdb.md。
//
// 输出：
//   VERDICT=BUG close_returned_early closeMs=0      buggy 侧
//   VERDICT=OK  close_waited         closeMs=150+   fixed 侧
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/boltdb/bolt"
)

const holdMs = 150

func run(tag string) {
	path := filepath.Join(os.TempDir(), "bolt341_"+tag+".db")
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

	// 保持一个未提交的写事务，看 Close 会不会等它
	time.Sleep(holdMs * time.Millisecond)

	early := false
	select {
	case <-done:
		early = true
	default:
	}

	if early {
		// 不执行 Commit：buggy 侧提交会踩到已释放的 mmap 触发 SIGSEGV，
		// 那是附加现象，不是判据。
		fmt.Printf("VERDICT=BUG close_returned_early closeMs=%d\n", atomic.LoadInt64(&closeMs))
		return
	}

	tx.Commit()
	<-done
	fmt.Printf("VERDICT=OK close_waited closeMs=%d\n", atomic.LoadInt64(&closeMs))
}

func main() {
	run(os.Args[1])
}
