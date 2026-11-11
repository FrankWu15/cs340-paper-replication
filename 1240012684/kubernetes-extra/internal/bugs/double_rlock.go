// Minimal reproduction of Kubernetes fix commit
// c1b19fce903675b82e9fdd1befcc5f5d658bfe78
// "avoid dobule RLock() in cpumanager"
//
// Upstream patch (pkg/kubelet/cm/cpumanager/state/state_mem.go):
//
//   func (s *stateMemory) GetCPUSetOrDefault(containerID string) cpuset.CPUSet {
//   -  s.RLock()
//   -  defer s.RUnlock()
//   -
//      if res, ok := s.GetCPUSet(containerID); ok {
//          return res
//      }
//      ...
//   }
//
// GetCPUSet() takes s.RLock() itself.  Go's sync.RWMutex is writer-preferring:
// once a writer is queued, a second RLock() from the SAME goroutine blocks
// behind that writer, while the writer waits for the first RUnlock().  That is
// the circular wait.  The fix simply removes the two outer lock lines.
package bugs

import (
	"sync"
	"time"
)

// stateMemory mirrors the shape of k8s cpumanager's stateMemory.
type stateMemory struct {
	sync.RWMutex
	cpus map[string]string
}

func newStateMemory() *stateMemory {
	return &stateMemory{cpus: map[string]string{"container-0": "0-3"}}
}

// getCPUSet is the inner method that acquires RLock itself (unchanged upstream).
func (s *stateMemory) getCPUSet(id string) (string, bool) {
	s.RLock()
	defer s.RUnlock()
	v, ok := s.cpus[id]
	return v, ok
}

// getCPUSetOrDefaultBuggy is the pre-fix version: outer RLock + nested RLock.
// The hook runs while the outer RLock is held; it is a deterministic
// scheduling point that lets a writer enter the wait queue (see README D4).
func (s *stateMemory) getCPUSetOrDefaultBuggy(id string, hook func()) (string, bool) {
	s.RLock()
	defer s.RUnlock()
	if hook != nil {
		hook()
	}
	return s.getCPUSet(id)
}

// getCPUSetOrDefaultFixed is the patched version: no outer lock at all.
func (s *stateMemory) getCPUSetOrDefaultFixed(id string) (string, bool) {
	return s.getCPUSet(id)
}

// RunDoubleRLock executes one trial.  mode is "buggy" or "fixed".
func RunDoubleRLock(mode string, trace func(format string, args ...any)) (string, error) {
	s := newStateMemory()
	outerLocked := make(chan struct{})
	writerQueued := make(chan struct{})
	writerDone := make(chan struct{})

	// A writer wants the exclusive lock.  It is released only after it has
	// been armed by the reader's hook, so the ordering is deterministic.
	go func() {
		<-outerLocked
		close(writerQueued)
		s.Lock()
		s.cpus["container-0"] = "4-7"
		s.Unlock()
		close(writerDone)
	}()

	hook := func() {
		close(outerLocked)
		<-writerQueued
		// Let the writer actually enter sync.RWMutex.Lock's wait queue.
		// The paper explicitly allows manually added sleeps for deterministic
		// reproduction (Section 4); see docs in README (deviation D4).
		time.Sleep(5 * time.Millisecond)
	}

	var value string
	var ok bool
	if mode == "fixed" {
		hook()
		value, ok = s.getCPUSetOrDefaultFixed("container-0")
	} else {
		value, ok = s.getCPUSetOrDefaultBuggy("container-0", hook)
	}
	trace("event=reader_returned value=%s found=%v", value, ok)

	<-writerDone
	trace("event=writer_returned")
	return value, nil
}
