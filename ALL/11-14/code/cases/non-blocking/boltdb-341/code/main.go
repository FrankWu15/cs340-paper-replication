package main

// BoltDB Bug #2 —— Close 不等待未完成的写事务
// 对应修复 commit: c69cb102（merge PR #377 "close-race"，实际改动在 e929eba）
// buggy commit:    55af28c19cd84431e1f3c5b132a07c1deecff10b
//
// 机理：DB.Close() 只拿 metalock 就执行 db.close()——置 opened=false、freelist=nil、
//       unmap 数据区、关闭文件描述符，完全不理会还有写事务没提交。
//       写事务随后 Commit 时访问已被清空/解除映射的内部结构，产生竞争或崩溃。
// 修复：Close() 增加 rwlock.Lock()，与写事务互斥，从而等到写事务结束再关。
//
// 运行：go build && ./repro

import (
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/boltdb/bolt"
)

var (
	path = flag.String("path", "/tmp/bolt-b2.db", "db 文件路径")
	wait = flag.Int("wait", 50, "Close 与事务提交之间的间隔(毫秒)")
)

func main() {
	flag.Parse()
	os.Remove(*path)

	db, err := bolt.Open(*path, 0600, nil)
	if err != nil {
		panic(err)
	}
	fmt.Println("[1] Open 成功:", *path)

	if err := db.Update(func(tx *bolt.Tx) error {
		_, e := tx.CreateBucketIfNotExists([]byte("b"))
		return e
	}); err != nil {
		panic(err)
	}
	fmt.Println("[2] 建 bucket 成功")

	// 打开一个写事务，先不提交
	tx, err := db.Begin(true)
	if err != nil {
		panic(err)
	}
	b := tx.Bucket([]byte("b"))
	if err := b.Put([]byte("k1"), []byte("v1")); err != nil {
		panic(err)
	}
	fmt.Println("[3] 写事务已打开并写入 k1（尚未提交）")

	closeDone := make(chan time.Duration, 1)
	go func() {
		start := time.Now()
		_ = db.Close() // buggy: 立刻返回；fixed: 阻塞到写事务结束
		closeDone <- time.Since(start)
	}()

	time.Sleep(time.Duration(*wait) * time.Millisecond)

	select {
	case d := <-closeDone:
		fmt.Printf("[4] Close 在写事务未提交时就返回了，耗时 %v  <-- buggy 行为\n", d)
	default:
		fmt.Println("[4] Close 正在等待写事务结束  <-- fixed 行为")
	}

	// 继续使用这个写事务：buggy 版本此时 db 内部已被清空，会崩
	fmt.Println("[5] 写事务继续写入并提交 ...")
	if err := b.Put([]byte("k2"), []byte("v2")); err != nil {
		fmt.Println("    Put 返回错误:", err)
	}
	if err := tx.Commit(); err != nil {
		fmt.Println("    Commit 返回错误:", err)
	} else {
		fmt.Println("    Commit 成功")
	}

	select {
	case d := <-closeDone:
		fmt.Printf("[6] Close 最终耗时 %v\n", d)
	case <-time.After(3 * time.Second):
		fmt.Println("[6] Close 3 秒内仍未返回")
	}
	fmt.Println("结论: 未崩溃")
}
