// Fixed side of etcd#5509 (upstream fix 1d88130522).
//
// The fix takes r.mu before client.mu.RLock in acquire(), so both paths use
// the same lock order (r.mu -> client.mu) and the ABBA cycle disappears.
// This driver runs the same two operations 500 times concurrently and expects
// every round to finish.
package main

import (
	"errors"
	"fmt"
	"sync"
)

type client struct {
	mu     sync.RWMutex
	conn   int
	cancel func()
}

func (c *client) ActiveConnection() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.conn
}

func (c *client) retryConnection() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.conn++
}

type remoteClient struct {
	client *client
	conn   int
	mu     sync.Mutex
}

// acquire now takes r.mu first, matching reconnect()'s order.
func (r *remoteClient) acquire() error {
	r.mu.Lock()
	active := r.client.ActiveConnection()
	match := r.conn == active
	r.mu.Unlock()
	if !match {
		return errors.New("connection changed under us")
	}
	return nil
}

func (r *remoteClient) reconnect() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.client.retryConnection()
	// tryUpdate() in the real client refreshes the cached connection the same
	// way, so a following acquire() sees a matching pair.
	r.conn = r.client.ActiveConnection()
}

func main() {
	const rounds = 500
	c := &client{conn: 1, cancel: func() {}}
	r := &remoteClient{client: c, conn: 1}

	ok, changed := 0, 0
	for i := 0; i < rounds; i++ {
		var wg sync.WaitGroup
		var mu sync.Mutex
		wg.Add(2)
		go func() {
			defer wg.Done()
			if err := r.acquire(); err != nil {
				mu.Lock()
				changed++
				mu.Unlock()
				return
			}
			mu.Lock()
			ok++
			mu.Unlock()
		}()
		go func() {
			defer wg.Done()
			r.reconnect()
		}()
		wg.Wait()
	}
	fmt.Printf("rounds=%d acquire_ok=%d conn_changed=%d\n", rounds, ok, changed)
	fmt.Println("no deadlock detected")
}
