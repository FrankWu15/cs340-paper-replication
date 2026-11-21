// Reproduction of etcd#5509 (fix commit 1d88130522).
//
// Transcribed from clientv3/remote_client.go and clientv3/client.go at the
// buggy parent (1d88130522^):
//
//	acquire():           client.mu.RLock()  then  r.mu.Lock()
//	reconnect()/retry(): r.mu.Lock()        then  client.mu.Lock()   (write)
//
// Two goroutines taking the two locks in opposite orders form an ABBA cycle.
// Because one side needs the *write* lock, the two readers cannot both pass,
// so the cycle always closes. The interleaving is forced with two handshakes
// so the run is deterministic instead of probabilistic.
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

// retryConnection is the write-lock path reached from reconnect().
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

var (
	acqHeld = make(chan struct{}) // acquire() holds client.mu.RLock
	recHeld = make(chan struct{}) // reconnect() holds r.mu
	done    = make(chan struct{})
)

// acquire mirrors the buggy upstream order: read lock first, then r.mu.
func (r *remoteClient) acquire() error {
	r.client.mu.RLock()
	close(acqHeld)
	<-recHeld
	r.mu.Lock()
	match := r.conn == r.client.conn
	r.mu.Unlock()
	if !match {
		r.client.mu.RUnlock()
		return errors.New("connection changed under us")
	}
	return nil // caller would keep the read lock and release it later
}

// reconnect mirrors upstream reconnect(): r.mu held across the call into the
// client, which needs the client write lock.
func (r *remoteClient) reconnect() {
	<-acqHeld
	r.mu.Lock()
	defer r.mu.Unlock()
	close(recHeld)
	r.client.retryConnection()
	fmt.Println("reconnect: done")
}

func main() {
	c := &client{conn: 1, cancel: func() {}}
	r := &remoteClient{client: c, conn: 1}

	go func() {
		fmt.Println("get: acquire -> client.mu.RLock, then r.mu.Lock")
		if err := r.acquire(); err != nil {
			fmt.Println("get: error:", err)
		} else {
			fmt.Println("get: acquire ok")
		}
		close(done)
	}()
	go func() {
		fmt.Println("watch: reconnect -> r.mu.Lock, then client.mu.Lock")
		r.reconnect()
	}()

	<-done
	fmt.Println("main: done")
}
