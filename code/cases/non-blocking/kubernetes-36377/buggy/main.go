// k8s#36377 —— store 返回的是共享指针，reconcile 直接改它，和读者并发读写同一个 map。
//
// 原代码 federation/pkg/federation-controller/namespace/namespace_controller.go：
//   baseNamespaceObj, exist, err := nc.namespaceInformerStore.GetByKey(namespace)
//   baseNamespace := baseNamespaceObj.(*api_v1.Namespace)
//   ... 直接修改 baseNamespace 的字段 ...
// GetByKey 返回的是 informer store 内部的同一个对象，锁只保护取指针这一步，
// 不保护对象内容。reconcile 写、其他读者读，落到同一个 map 上就是数据竞争，
// Go 运行时直接 fatal: concurrent map read and map write。
//
// 补丁 647b826d 的做法：先从 store 取对象，再 DeepCopy 一份，之后只改副本。
package main

import (
	"fmt"
	"os"
	"sync"
)

type Namespace struct {
	Name        string
	Annotations map[string]string
}

func (ns *Namespace) DeepCopy() *Namespace {
	cp := &Namespace{Name: ns.Name, Annotations: make(map[string]string, len(ns.Annotations))}
	for k, v := range ns.Annotations {
		cp.Annotations[k] = v
	}
	return cp
}

type Store struct {
	mu  sync.RWMutex
	obj *Namespace
}

func (s *Store) GetByKey(key string) (*Namespace, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.obj, true, nil // ← 返回共享指针
}

func (s *Store) snapshotAnnotations() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.obj.Annotations)
}

// reconcile 复刻原实现：拿到对象后直接改。
func reconcile(store *Store, key string) {
	obj, exist, err := store.GetByKey(key)
	if err != nil || !exist {
		return
	}
	ns := obj
	ns.Annotations["federation.kubernetes.io/replicated"] = "true" // ← 改到了 store 内部对象
}

func main() {
	store := &Store{obj: &Namespace{Name: "ns1", Annotations: map[string]string{"keep": "1"}}}

	var wg sync.WaitGroup
	wg.Add(2)

	// 读者：多次从 store 取对象并读 map
	go func() {
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			obj, _, _ := store.GetByKey("ns1")
			_ = len(obj.Annotations)
		}
	}()

	// 写者：reconcile 反复改同一个对象
	go func() {
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			reconcile(store, "ns1")
		}
	}()

	wg.Wait()

	// 即使没触发运行时检测，共享对象被改写本身就是错的
	if n := store.snapshotAnnotations(); n != 1 {
		fmt.Println("VERDICT: BUG")
		fmt.Printf("store 里的对象被 reconcile 改写：annotations 从 1 个变成 %d 个\n", n)
		os.Exit(3)
	}
	fmt.Println("VERDICT: OK")
}
