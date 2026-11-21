// docker#8909 修复版 —— 与 buggy 的唯一差别是直接读字段，不再调 GetExitCode()。
//
// 对应上游补丁 03ea2166：
//   -  if code == container.GetExitCode() {
//   +  if code == container.ExitCode {
package main

import (
	"fmt"
	"os"
	"sync"
	"time"
)

type Container struct {
	mu       sync.Mutex
	Name     string
	Running  bool
	ExitCode int
}

func (c *Container) Lock()   { c.mu.Lock() }
func (c *Container) Unlock() { c.mu.Unlock() }

func (c *Container) GetExitCode() int {
	c.Lock()
	defer c.Unlock()
	return c.ExitCode
}

type Daemon struct {
	containers []*Container
}

func (d *Daemon) List(exited []int) []string {
	var out []string
	for _, c := range d.containers {
		c.Lock()
		if !c.Running && len(exited) > 0 {
			skip := true
			for _, code := range exited {
				if code == c.ExitCode { // 修复点：调用方已持锁，直接读字段
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
		fmt.Println("DEADLOCK: Containers() 3s 未返回")
		os.Exit(2)
	}
}
