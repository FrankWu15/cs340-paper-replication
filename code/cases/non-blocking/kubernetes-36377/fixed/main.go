// k8s#36377 修复版 —— 取到对象后先 DeepCopy，只改副本，store 内部对象保持不变，
// 读者与写者不再落到同一个 map 上。
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
	return s.obj, true, nil
}

func (s *Store) snapshotAnnotations() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.obj.Annotations)
}

// reconcile 对应补丁后的实现：先拷贝，再改副本。
func reconcile(store *Store, key string) {
	obj, exist, err := store.GetByKey(key)
	if err != nil || !exist {
		return
	}
	ns := obj.DeepCopy() // ← 修复点
	ns.Annotations["federation.kubernetes.io/replicated"] = "true"
}

func main() {
	store := &Store{obj: &Namespace{Name: "ns1", Annotations: map[string]string{"keep": "1"}}}

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			obj, _, _ := store.GetByKey("ns1")
			_ = len(obj.Annotations)
		}
	}()

	go func() {
		defer wg.Done()
		for i := 0; i < 100000; i++ {
			reconcile(store, "ns1")
		}
	}()

	wg.Wait()

	if n := store.snapshotAnnotations(); n != 1 {
		fmt.Println("VERDICT: BUG")
		fmt.Printf("store 对象被改写：annotations=%d\n", n)
		os.Exit(3)
	}
	fmt.Println("VERDICT: OK")
}
