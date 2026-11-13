// Package bugs contains faithful minimal reproductions of two etcd concurrency
// bugs from "Understanding Real-World Concurrency Bugs in Go" (ASPLOS'19).
//
// The code below is a line-for-line transcription of the upstream functions
// involved in each bug, taken from the buggy commit (the parent of the
// fix commit). The fix commit's one-line change is provided as a second mode
// so the same driver exercises buggy vs. fixed behaviour.
//
// Source provenance (verified via `git log` on github.com/etcd-io/etcd):
//   etcd#6873  -> fix commit 7618fdd1d642e47cac70c03f637b0fd798a53a6e (2016-11-18)
//                 buggy state: parent 377f19b0031f9c0aafe2aec28b6f9019311f52f9
//                 file: proxy/grpcproxy/watch_broadcasts.go
package bugs

import (
	"sync"
)

// ---------------------------------------------------------------------------
// etcd#6873 — grpcproxy: deadlock on watch broadcasts stop
// ---------------------------------------------------------------------------
// Upstream type (fields relevant to the bug):
//
//	type watchBroadcasts struct {
//		mu       sync.Mutex
//		bcasts   map[*watchBroadcast]struct{}
//		updatec  chan *watchBroadcast
//		donec    chan struct{}
//	}
//
// Buggy stop() (as committed, before fix 7618fdd1):
//
//	func (wbs *watchBroadcasts) stop() {
//		wbs.mu.Lock()
//		defer wbs.mu.Unlock()
//		for wb := range wbs.bcasts { wb.stop() }
//		wbs.bcasts = nil
//		close(wbs.updatec)
//		<-wbs.donec
//	}
//
// The coalesce loop started in newWatchBroadcasts runs:
//
//	go func() {
//		defer close(wbs.donec)
//		for wb := range wbs.updatec { wbs.coalesce(wb) }
//	}()
//
// and coalesce() does wbs.mu.Lock() before it can finish. Holding mu across
// the `<-wbs.donec` wait means the coalesce loop can never exit -> deadlock.

type wbs6873 struct {
	mu      sync.Mutex
	bcasts  int // number of broadcasts registered
	updatec chan struct{}
	donec   chan struct{}
}

func newWBS6873() *wbs6873 {
	wbs := &wbs6873{
		updatec: make(chan struct{}, 1),
		donec:   make(chan struct{}),
	}
	// coalesce loop (transcribed from newWatchBroadcasts)
	go func() {
		defer close(wbs.donec)
		for range wbs.updatec {
			wbs.coalesce6873()
		}
	}()
	return wbs
}

func (wbs *wbs6873) coalesce6873() {
	wbs.mu.Lock() // <-- blocked forever when stop() holds mu
	// (coalesce work would happen here)
	wbs.mu.Unlock()
}

// StopBuggy is the upstream buggy stop().
func (wbs *wbs6873) StopBuggy() {
	wbs.mu.Lock()
	defer wbs.mu.Unlock()
	wbs.bcasts = 0
	close(wbs.updatec)
	<-wbs.donec // deadlock: coalesce loop needs mu to close donec
}

// StopFixed is the upstream fixed stop() (fix 7618fdd1): mu.Unlock() moved
// before the <-donec wait.
func (wbs *wbs6873) StopFixed() {
	wbs.mu.Lock()
	for i := 0; i < wbs.bcasts; i++ { /* wb.stop() */
	}
	wbs.bcasts = 0
	close(wbs.updatec)
	wbs.mu.Unlock() // <-- released before waiting on donec
	<-wbs.donec
}

// Trigger6873 drives the buggy/fixed stop under the exact production call
// pattern: a coalesce is in flight (the loop is parked waiting on mu) while
// stop() holds mu and waits on donec. With the buggy version this is a
// deterministic "all goroutines asleep" deadlock; with the fixed version the
// loop exits and stop() returns.
func Trigger6873(fixed bool) {
	wbs := newWBS6873()
	wbs.bcasts = 1
	// Enqueue a coalesce so the loop is inside coalesce6873() wanting mu.
	wbs.updatec <- struct{}{}
	if fixed {
		wbs.StopFixed()
	} else {
		wbs.StopBuggy()
	}
}
