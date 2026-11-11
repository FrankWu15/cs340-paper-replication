// Minimal reproduction of Kubernetes fix commit
// d3639aff7397dd0f0d3553b82043401ff834a356
// "Fix deadlock in watch cache"
//
// Upstream patch (pkg/storage/watch_cache.go):
//
//   w.RLock()
// + defer w.RUnlock()
//   for w.resourceVersion < resourceVersion {
//       if w.clock.Since(startTime) >= MaximumListWait {
//           return nil, 0, fmt.Errorf("time limit exceeded ...")
//       }
//       w.cond.Wait()
//   }
// - defer w.RUnlock()
//
// Before the fix, the error path returned before `defer w.RUnlock()` was
// registered, leaking the read lock forever.  Any later writer then blocks.
package bugs

import (
	"errors"
	"sync"
)

type watchCache struct {
	sync.RWMutex
	resourceVersion uint64
	target          uint64
}

// waitUntilFreshAndList reproduces the control flow of the upstream method.
// timedOut forces the error path that the fix was about.
func (w *watchCache) waitUntilFreshAndList(mode string, timedOut bool) (uint64, error) {
	w.RLock()
	if mode == "fixed" {
		// The fix: register the unlock immediately after acquiring the lock.
		defer w.RUnlock()
	}
	if timedOut {
		return 0, errors.New("time limit exceeded while waiting for resource version")
	}
	// Normal path (not exercised in this minimal reproduction).
	if mode != "fixed" {
		defer w.RUnlock()
	}
	w.resourceVersion = w.target
	return w.resourceVersion, nil
}

// RunMissUnlock executes one trial.  mode is "buggy" or "fixed".
func RunMissUnlock(mode string, trace func(format string, args ...any)) (string, error) {
	w := &watchCache{resourceVersion: 0, target: 10}

	// The first call always takes the error path.  In the buggy version it
	// leaks w.RLock(); in the fixed version the deferred unlock fires.
	_, err := w.waitUntilFreshAndList(mode, true)
	trace("event=first_call_returned err=%v", err)

	// A later writer needs the exclusive lock.  It completes only if the
	// read lock was released.
	done := make(chan struct{})
	go func() {
		w.Lock()
		w.resourceVersion = 99
		w.Unlock()
		close(done)
	}()
	<-done
	trace("event=writer_returned")
	return "writer_completed", nil
}
