package main

// BoltDB Bug #3 —— beginTx 错误分支不释放 metalock
// 对应修复 commit: defdb743cdca840890fea24c3111a7bffe5cc0a3（"Fix deadlock on remmap"）
// buggy commit:    01bc9be72f46f0f1978b1f1581440c399b3a7684
//
// 机理：buggy 版 beginTx() 先拿 mmaplock.RLock() 再拿 metalock.Lock()；
//       当 db.opened == false（Close 之后）时，只 RUnlock 就 return，
//       漏了 metalock.Unlock()，metalock 被永久占用，之后任何事务操作都会卡死。
// 修复：beginTx 里把 metalock 提前到 mmaplock 之前，并在错误分支补上 Unlock。
//
// 运行：
//   ./repro -mode closed    # 主实验：Close 之后再 Begin，触发死锁
//   ./repro -mode remap     # 附实验：读事务与 mmap 重映射并发压测

import (
	"flag"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/boltdb/bolt"
)

var (
	mode = flag.String("mode", "closed", "触发模式: closed | remap")
	path = flag.String("path", "/tmp/bolt-b3.db", "db 文件路径")
	secs = flag.Int("secs", 20, "remap 模式压测秒数")
)

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func main() {
	flag.Parse()
	os.Remove(*path)

	db, err := bolt.Open(*path, 0600)
	must(err)
	fmt.Println("[1] Open 成功:", *path)

	must(db.Update(func(tx *bolt.Tx) error {
		_, e := tx.CreateBucketIfNotExists([]byte("b"))
		return e
	}))
	fmt.Println("[2] 建 bucket 成功")

	switch *mode {
	case "closed":
		runClosed(db)
	case "remap":
		runRemap(db)
	default:
		fmt.Println("未知模式:", *mode)
		os.Exit(2)
	}
}

// --- 模式一：Close 之后再 Begin ---
func runClosed(db *bolt.DB) {
	must(db.Close())
	fmt.Println("[3] Close 完成")

	_, err := db.Begin(false)
	fmt.Printf("[4] 第 1 次 Begin(false) 返回: %v  <-- 期望 ErrDatabaseNotOpen\n", err)

	fmt.Println("[5] 第 2 次 Begin(false)，buggy 版本会卡死在这里 ...")
	start := time.Now()
	_, err = db.Begin(false)
	fmt.Printf("[6] 第 2 次 Begin(false) 返回: %v (耗时 %v)\n", err, time.Since(start))
	fmt.Println("结论: 未卡死")
}

// --- 模式二：读事务 vs mmap 重映射 ---
func runRemap(db *bolt.DB) {
	var (
		stop    int32
		rounds  int32
		readers = 4
		wg      sync.WaitGroup
	)

	for i := 0; i < readers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for atomic.LoadInt32(&stop) == 0 {
				tx, err := db.Begin(false)
				if err != nil {
					continue
				}
				time.Sleep(2 * time.Millisecond) // 放大 RLock 持有窗口
				tx.Rollback()
			}
		}()
	}

	val := make([]byte, 256*1024)
	wg.Add(1)
	go func() {
		defer wg.Done()
		i := 0
		for atomic.LoadInt32(&stop) == 0 {
			i++
			err := db.Update(func(tx *bolt.Tx) error {
				b := tx.Bucket([]byte("b"))
				return b.Put([]byte(fmt.Sprintf("key-%08d", i)), val)
			})
			if err != nil {
				fmt.Println("Update 出错:", err)
			}
			atomic.AddInt32(&rounds, 1)
			time.Sleep(1 * time.Millisecond)
		}
	}()

	start := time.Now()
	deadline := start.Add(time.Duration(*secs) * time.Second)
	for time.Now().Before(deadline) {
		time.Sleep(2 * time.Second)
		fmt.Printf("  已运行 %2.0fs  写入 %d 次\n", time.Since(start).Seconds(), atomic.LoadInt32(&rounds))
	}

	atomic.StoreInt32(&stop, 1)
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
		fmt.Println("结论: 未卡死")
	case <-time.After(10 * time.Second):
		fmt.Println("结论: 收尾阶段卡住（疑似死锁）")
		os.Exit(3)
	}
}
