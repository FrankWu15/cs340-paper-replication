// docker#28682 —— ready 与 ctx.Done 同时就绪时，select 会随机选一个，
// 选中 ctx.Done 就漏掉 close stdin，容器 stdin 永远不关闭。
//
// 原代码 libcontainerd/container_unix.go 的 start()：
//   go func() {
//       select {
//       case <-ready:
//           ctr.sendCloseStdin()
//       case <-ctx.Done():
//       }
//   }()
// 当容器很快就绪、同时又立刻被停止时，两个 case 同时可执行，Go 的 select
// 等概率随机选择 —— 约一半的概率走到空分支，close stdin 丢失。
//
// 补丁 4e262f63 改成两段式：先等 ready 或 ctx.Done，再单独判断 ready 是否
// 已就绪（closed channel 永远可读），就绪就补发一次。
package main

import (
	"context"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
)

type container struct {
	mu         sync.Mutex
	stdinClose int
}

func (c *container) sendCloseStdin() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.stdinClose++
}

func (c *container) closed() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.stdinClose
}

// start 复刻原实现。
func start(ctx context.Context, ready <-chan struct{}, ctr *container, wg *sync.WaitGroup) {
	go func() {
		defer wg.Done()
		select {
		case <-ready:
			ctr.sendCloseStdin()
		case <-ctx.Done():
			// 容器已停止，什么都不做 —— close stdin 被跳过
		}
	}()
}

func main() {
	const trials = 200
	var missed int64

	for i := 0; i < trials; i++ {
		ctr := &container{}
		ready := make(chan struct{})
		ctx, cancel := context.WithCancel(context.Background())

		var wg sync.WaitGroup
		wg.Add(1)

		// 两种事件"同时"发生：ready 关闭后立刻 cancel
		close(ready)
		cancel()
		start(ctx, ready, ctr, &wg)
		wg.Wait()

		if ctr.closed() == 0 {
			atomic.AddInt64(&missed, 1)
		}
	}

	fmt.Printf("trials=%d missed_close_stdin=%d\n", trials, missed)

	if missed > 0 {
		fmt.Println("VERDICT: BUG")
		fmt.Printf("%d/%d 次未发送 close stdin：select 选中 ctx.Done，ready 分支被丢弃\n", missed, trials)
		os.Exit(3)
	}
	fmt.Println("VERDICT: OK")
}
