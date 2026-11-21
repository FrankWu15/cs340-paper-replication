// k8s#30872 修复版 —— 锁内只取 informer 列表，锁外再调 HasSynced()，
// 回调拿锁时外层已经不持锁，不再自死锁。
package main

import (
	"fmt"
	"os"
	"sync"
	"time"
)

type informer struct {
	synced bool
	onSync func()
}

func (i *informer) HasSynced() bool {
	if i.onSync != nil {
		i.onSync()
	}
	return i.synced
}

type federatedInformer struct {
	mu              sync.Mutex
	targetInformers map[string]*informer
	updates         int
}

func (f *federatedInformer) NotifyClusterUpdate() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.updates++
}

// ClustersSynced 对应补丁后的实现。
func (f *federatedInformer) ClustersSynced(clusters []string) bool {
	okSoFar, informersToCheck := func() (bool, []*informer) {
		f.mu.Lock()
		defer f.mu.Unlock()

		if len(f.targetInformers) != len(clusters) {
			return false, nil
		}
		list := make([]*informer, 0, len(clusters))
		for _, name := range clusters {
			in, found := f.targetInformers[name]
			if !found {
				return false, nil
			}
			list = append(list, in)
		}
		return true, list
	}()

	if !okSoFar {
		return false
	}

	// 锁外检查：HasSynced 的回调可以安全地拿锁
	for _, in := range informersToCheck {
		if !in.HasSynced() {
			return false
		}
	}
	return true
}

func main() {
	f := &federatedInformer{targetInformers: map[string]*informer{}}
	for _, name := range []string{"cluster-a", "cluster-b"} {
		in := &informer{synced: true}
		in.onSync = f.NotifyClusterUpdate
		f.targetInformers[name] = in
	}

	done := make(chan bool, 1)
	go func() { done <- f.ClustersSynced([]string{"cluster-a", "cluster-b"}) }()

	select {
	case ok := <-done:
		fmt.Printf("VERDICT: OK\nsynced=%v updates=%d\n", ok, f.updates)
	case <-time.After(3 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		os.Exit(2)
	}
}
