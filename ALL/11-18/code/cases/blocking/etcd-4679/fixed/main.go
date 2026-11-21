// Fixed side of etcd#4679 (upstream fix d21d2e6624).
//
// The fix drops the deferred unlock and releases c.mu *before* closing the
// watcher, the lease and the connection, so the watch goroutine can take the
// lock it needs on the way out.
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
	if c.cancel == nil {
		c.mu.Unlock()
		return nil
	}
	c.cancel()
	c.cancel = nil
	c.mu.Unlock()

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
