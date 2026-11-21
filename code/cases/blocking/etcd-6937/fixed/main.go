// Fixed side of etcd#6937 (upstream fix 91ff6f30b5).
//
// The only change from the buggy side is that bcast() and delete() read
// len(wb.receivers) directly instead of calling size()/empty(), so the
// goroutine never tries to take the read lock it already holds as a writer.
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
	if len(wb.receivers) > 0 {
		wb.coalesced += len(wb.receivers) - 1
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
	if len(wb.receivers) > 0 {
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
	fmt.Println("bcast: enter (holds wb.mu.Lock, reads len(receivers) directly)")
	wb.bcast()
	fmt.Printf("bcast: done, responses=%d coalesced=%d\n", wb.responses, wb.coalesced)
	wb.delete(w2)
	fmt.Printf("delete: done, receivers=%d\n", wb.size())
}
