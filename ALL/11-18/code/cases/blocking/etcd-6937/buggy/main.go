// Reproduction of etcd#6937 (fix commit 91ff6f30b5).
//
// Transcribed from proxy/grpcproxy/watch_broadcast.go at the buggy parent
// (91ff6f30b5^). bcast() and delete() both hold the write lock and then call
// size()/empty(), which take the read lock on the same sync.RWMutex.
// sync.RWMutex is not reentrant, so the goroutine blocks on itself and the
// runtime reports "all goroutines are asleep - deadlock!".
package main

import (
	"fmt"
	"sync"
)

type watcher struct{ id int64 }

func (w *watcher) send() {}

type watchBroadcast struct {
	mu        sync.RWMutex
	receivers map[*watcher]struct{}
	nextrev   int64
	responses int
	coalesced int
}

func newWatchBroadcast() *watchBroadcast {
	return &watchBroadcast{receivers: make(map[*watcher]struct{})}
}

func (wb *watchBroadcast) bcast() {
	wb.mu.Lock()
	defer wb.mu.Unlock()
	if wb.responses > 0 || wb.nextrev == 0 {
		wb.nextrev++
	}
	wb.responses++
	for r := range wb.receivers {
		r.send()
	}
	// BUG: size() takes wb.mu.RLock() while this goroutine holds wb.mu.Lock().
	if wb.size() > 0 {
		wb.coalesced += wb.size() - 1
	}
}

func (wb *watchBroadcast) add(w *watcher) {
	wb.mu.Lock()
	defer wb.mu.Unlock()
	wb.receivers[w] = struct{}{}
}

func (wb *watchBroadcast) delete(w *watcher) {
	wb.mu.Lock()
	defer wb.mu.Unlock()
	delete(wb.receivers, w)
	// BUG: empty() -> size() -> RLock, same self-deadlock as bcast().
	if !wb.empty() {
		wb.coalesced--
	}
}

func (wb *watchBroadcast) size() int {
	wb.mu.RLock()
	defer wb.mu.RUnlock()
	return len(wb.receivers)
}

func (wb *watchBroadcast) empty() bool { return wb.size() == 0 }

func main() {
	wb := newWatchBroadcast()
	w1, w2 := &watcher{id: 1}, &watcher{id: 2}
	wb.add(w1)
	wb.add(w2)
	fmt.Printf("watchBroadcast ready: receivers=%d\n", len(wb.receivers))
	fmt.Println("bcast: enter (holds wb.mu.Lock, then calls size() -> RLock)")
	wb.bcast()
	fmt.Printf("bcast: done, responses=%d coalesced=%d\n", wb.responses, wb.coalesced)
	wb.delete(w2)
	fmt.Printf("delete: done, receivers=%d\n", wb.size())
}
