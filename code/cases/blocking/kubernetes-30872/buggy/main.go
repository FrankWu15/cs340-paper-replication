// k8s#30872 —— 持锁时调用 HasSynced()，其回调又去拿同一把锁，形成自死锁。
//
// 原代码 federation/pkg/federation-controller/util/federated_informer.go：
// ClustersSynced() 先 fs.federatedInformer.Lock()，然后在锁内遍历
// targetInformers 调 targetInformer.HasSynced()。而 HasSynced 会触发
// informer 的同步回调，回调路径最终又要拿同一把锁 —— sync.Mutex 不可重入，卡死。
//
// 补丁 681d1530 的做法：在锁内只把要检查的 informer 列表拷出来，
// 解锁之后再逐个调 HasSynced()。
package main

import (
	"fmt"
	"os"
	"sync"
	"time"
)

// informer 对应 k8s 的 cache.SharedIndexInformer。
type informer struct {
	synced bool
	onSync func() // 同步时的回调，会回到父结构的更新路径
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

// NotifyClusterUpdate 是回调的落点：它需要同一把锁。
func (f *federatedInformer) NotifyClusterUpdate() {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.updates++
}

// ClustersSynced 复刻原实现：整个检查都在锁内。
func (f *federatedInformer) ClustersSynced(clusters []string) bool {
	f.mu.Lock()
	defer f.mu.Unlock()

	if len(f.targetInformers) != len(clusters) {
		return false
	}
	for _, name := range clusters {
		in, found := f.targetInformers[name]
		if !found {
			return false
		}
		if !in.HasSynced() { // ← 回调 → NotifyClusterUpdate → 再次 Lock
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
		fmt.Println("ClustersSynced 卡在 HasSynced 回调里：外层已持锁，回调再次加锁")
		os.Exit(2)
	}
}
