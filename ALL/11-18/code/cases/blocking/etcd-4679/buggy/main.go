// Reproduction of etcd#4679 (fix commit d21d2e6624).
//
// Transcribed from clientv3/client.go at the buggy parent (d21d2e6624^):
//
//	func (c *Client) Close() error {
//	    c.mu.Lock()
//	    defer c.mu.Unlock()      // <- lock held across every Close below
//	    if c.cancel == nil { return nil }
//	    c.cancel(); c.cancel = nil
//	    c.Watcher.Close()        // waits for the watch goroutine to return
//	    c.Lease.Close()
//	    return c.conn.Close()
//	}
//
// The watch goroutine needs c.mu on its way out, so Close waits for a
// goroutine that is waiting for the lock Close still holds.
package main

import (
	"fmt"
	"sync"
)

type conn struct{}

func (c *conn) Close() error { return nil }

type watcher struct {
	closec chan struct{}
	donec  chan struct{}
}

type client struct {
	mu      sync.Mutex
	cancel  func()
	conn    *conn
	watcher *watcher
	gen     int
}

func (w *watcher) run(c *client) {
	<-w.closec
	// The real client touches shared state (ActiveConnection / retry bookkeeping)
	// before the watch goroutine can finish.
	c.mu.Lock()
	c.gen++
	c.mu.Unlock()
	close(w.donec)
}

func (w *watcher) Close() {
	close(w.closec)
	<-w.donec
}

func newClient() *client {
	c := &client{cancel: func() {}, conn: &conn{}}
	c.watcher = &watcher{closec: make(chan struct{}), donec: make(chan struct{})}
	go c.watcher.run(c)
	return c
}

func (c *client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cancel == nil {
		return nil
	}
	c.cancel()
	c.cancel = nil
	fmt.Println("close: waiting for watcher to stop")
	c.watcher.Close()
	c.conn.Close()
	return nil
}

func main() {
	c := newClient()
	fmt.Println("client ready, calling Close")
	if err := c.Close(); err != nil {
		fmt.Println("close error:", err)
		return
	}
	fmt.Println("close ok")
}
