// Package repro contains a minimal, source-faithful extraction of the
// cockroachdb blocking bug reproduced in this project.
//
// Upstream bug: commit 1cc699802557f67d4464de391b7350a527f9f445
//   "Call g.mu.Unlock() before calling break"
//   file: gossip/gossip.go  (funcs (g *Gossip) bootstrap() and manage())
//   category: blocking (deadlock) — cockroachdb has 12 such bugs in the paper.
//
// Root cause: the bootstrap loop acquires g.mu.Lock(); when g.closed it
// `break`s WITHOUT releasing the mutex. The fix inserts `g.mu.Unlock()`
// before the `break`. Because the lock is leaked on the early exit, any
// later g.mu.Lock() (same or another goroutine) blocks forever -> deadlock.
//
// This extraction keeps ONLY the mutex + closed flag + the looping lock/break
// pattern; all unrelated gossip logic is omitted (see README deviations D1-D6).
package repro

import (
	"runtime"
	"sync"
)

// Gossip is a reduced stand-in for cockroachdb's gossip.Gossip struct,
// trimmed to the single mutex and the closed flag involved in the bug.
type Gossip struct {
	Mu     sync.Mutex
	Closed bool
}

// Bootstrap is a faithful minimal extraction of the buggy loop in
// cockroachdb/gossip/gossip.go (func (g *Gossip) bootstrap()).
//
//	fixed==false -> leaks g.Mu on the early break (the bug) -> deadlock.
//	fixed==true  -> releases g.Mu before the break (the fix) -> clean exit.
func Bootstrap(g *Gossip, fixed bool) {
	for {
		g.Mu.Lock()
		if g.Closed {
			if fixed {
				g.Mu.Unlock()
			}
			break
		}
		// stand-in for g.parseBootstrapAddresses() etc. in a normal iteration
		runtime.Gosched()
	}
}
