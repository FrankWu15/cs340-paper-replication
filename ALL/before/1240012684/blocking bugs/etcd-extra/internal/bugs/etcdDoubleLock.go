// ---------------------------------------------------------------------------
// etcd (2015-01, github.com/coreos/etcd client) — double lock in Sync()
// ---------------------------------------------------------------------------
// Upstream (buggy) code, file client/client.go, httpClusterClient:
//
//	func (c *httpClusterClient) Sync(ctx context.Context) error {
//		c.Lock()
//		defer c.Unlock()
//		mAPI := NewMembersAPI(c)
//		ms, err := mAPI.List(ctx)   // List -> Do -> c.Endpoints() -> c.RLock()
//		if err != nil { return err }
//		eps := make([]string, 0)
//		for _, m := range ms { eps = append(eps, m.ClientURLs...) }
//		c.endpoints = eps           // (pseudo)
//		return nil
//	}
//
// MembersAPI.List -> httpClusterClient.Do -> c.Endpoints() takes c.RLock().
// Holding c.Lock() (exclusive) while calling a path that takes c.RLock()
// self-deadlocks the single goroutine ("double lock" / singular circular bug).
//
// Fix (commit ae062a0825a4100d0cf9ac7c8bb0fa1ca69c6814): move c.Lock()/defer
// c.Unlock() to AFTER mAPI.List(ctx) returns.

package bugs

import (
	"context"
	"sync"
)

type httpClusterClientRepro struct {
	sync.RWMutex
	endpoints []string
}

func (c *httpClusterClientRepro) Endpoints() []string {
	c.RLock()
	defer c.RUnlock()
	return c.endpoints
}

// List reproduces MembersAPI.List -> Do -> Endpoints() (RLock path).
func (c *httpClusterClientRepro) List(ctx context.Context) ([]string, error) {
	// upstream Do() internally calls c.Endpoints(), which RLock()s the same mutex
	return c.Endpoints(), nil
}

// SyncBuggy is the upstream buggy Sync(): Lock held across List (which RLock's).
func (c *httpClusterClientRepro) SyncBuggy(ctx context.Context) error {
	c.Lock()
	defer c.Unlock()
	_, err := c.List(ctx) // List -> RLock() -> deadlock with the held Lock()
	if err != nil {
		return err
	}
	return nil
}

// SyncFixed is the upstream fixed Sync(): Lock acquired only after List returns.
func (c *httpClusterClientRepro) SyncFixed(ctx context.Context) error {
	_, err := c.List(ctx)
	if err != nil {
		return err
	}
	c.Lock()
	defer c.Unlock()
	return nil
}

// TriggerDoubleLock drives the double-lock bug or its fix.
func TriggerDoubleLock(fixed bool) {
	c := &httpClusterClientRepro{endpoints: []string{"http://127.0.0.1:2379"}}
	if fixed {
		_ = c.SyncFixed(context.Background())
	} else {
		_ = c.SyncBuggy(context.Background())
	}
}
