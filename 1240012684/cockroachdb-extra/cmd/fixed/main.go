// Command fixed reproduces cockroachdb commit 1cc699802557f67d4464de391b7350a527f9f445
// in its FIXED state: gossip.Bootstrap releases g.mu before breaking out of
// the loop. The lock is never leaked, so the program terminates cleanly with
// exit code 0.
package main

import (
	"fmt"
	"os"
	"time"

	"cockroachdbrepro/repro"
)

func main() {
	g := &repro.Gossip{Closed: true}

	done := make(chan struct{})
	go func() {
		repro.Bootstrap(g, true) // fixed: releases the lock before break
		close(done)
	}()

	// Watchdog kept for parity with the buggy driver; it must NOT fire here.
	go func() {
		<-time.After(8 * time.Second)
		fmt.Println("ERROR: fixed version unexpectedly deadlocked (watchdog)")
		os.Exit(2)
	}()

	<-done // bootstrap returned after cleanly unlocking g.Mu

	g.Mu.Lock()
	g.Mu.Unlock()
	fmt.Println("returned (fixed version exits 0)")
}
