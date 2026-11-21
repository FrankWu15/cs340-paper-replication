// docker#28682 修复版 —— 两段式 select：先等 ready 或 ctx.Done，
// 再单独判断 ready 是否已就绪，就绪就补发 close stdin，消除随机性。
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

// start 对应补丁后的实现。
func start(ctx context.Context, ready <-chan struct{}, ctr *container, wg *sync.WaitGroup) {
	go func() {
		defer wg.Done()
		select {
		case <-ready:
		case <-ctx.Done():
		}
		select {
		case <-ready:
			ctr.sendCloseStdin() // ready 已就绪就一定会走到这里
		default:
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
		os.Exit(3)
	}
	fmt.Println("VERDICT: OK")
}
