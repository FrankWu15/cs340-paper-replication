// docker#8909 —— 在持锁状态下调用会再次加锁的取值方法，导致自死锁。
//
// 原代码 daemon/list.go 的 Containers() 在遍历时已持有 container 的锁，
// 又调用 container.GetExitCode()，而后者内部再次 Lock 同一把 sync.Mutex。
// Go 的 sync.Mutex 不可重入，于是同一个 goroutine 永久阻塞在自己身上。
//
// 本文件按原结构重写为最小可运行体：Container 暴露 Lock/GetExitCode，
// Daemon.List 复刻"持锁遍历 + 调用取值方法"的调用序列。
package main

import (
	"fmt"
	"os"
	"sync"
	"time"
)

// Container 对应 moby 的 container.Container，锁与退出码都在同一个结构上。
type Container struct {
	mu       sync.Mutex
	Name     string
	Running  bool
	ExitCode int
}

func (c *Container) Lock()   { c.mu.Lock() }
func (c *Container) Unlock() { c.mu.Unlock() }

// GetExitCode 是原代码里的方法：自己先加锁再读字段。
func (c *Container) GetExitCode() int {
	c.Lock()
	defer c.Unlock()
	return c.ExitCode
}

type Daemon struct {
	containers []*Container
}

// List 复刻 Containers(job) 的关键路径：持锁、判断 exited 过滤器、
// 在锁内调用 GetExitCode()。
func (d *Daemon) List(exited []int) []string {
	var out []string
	for _, c := range d.containers {
		c.Lock()
		if !c.Running && len(exited) > 0 {
			skip := true
			for _, code := range exited {
				if code == c.GetExitCode() { // ← 同一把锁被再次获取
					skip = false
					break
				}
			}
			if skip {
				c.Unlock()
				continue
			}
		}
		if !c.Running {
			out = append(out, c.Name)
		}
		c.Unlock()
	}
	return out
}

func main() {
	d := &Daemon{containers: []*Container{
		{Name: "zero1", ExitCode: 0},
		{Name: "zero2", ExitCode: 0},
		{Name: "nonzero1", ExitCode: 1},
	}}

	done := make(chan []string, 1)
	go func() { done <- d.List([]int{0}) }()

	select {
	case names := <-done:
		fmt.Printf("VERDICT: OK\ncompleted: %v\n", names)
	case <-time.After(3 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		fmt.Println("Containers() 3s 未返回，卡在 lock 与 GetExitCode 的嵌套加锁")
		os.Exit(2)
	}
}
