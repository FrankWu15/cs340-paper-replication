// Command buggy reproduces cockroachdb commit 1cc699802557f67d4464de391b7350a527f9f445
// in its BROKEN state: gossip.Bootstrap breaks out of the loop while still
// holding g.Mu, leaking the lock. The next g.Mu.Lock() can never succeed, so
// the only remaining runnable goroutine blocks and Go's native deadlock
// detector prints "fatal error: all goroutines are asleep - deadlock!" and
// exits with code 2.
//
// By default no watchdog is used, so the exit-2 comes straight from the Go
// runtime's deadlock detector (the canonical signal for a blocking bug).
// Pass -watchdog to add an 8s fallback that force-exits 2 if the native
// detector were somehow suppressed (e.g. by a pending timer, as in the
// etcd netpoller case).
package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	"cockroachdbrepro/repro"
)

func main() {
	watchdog := flag.Bool("watchdog", false, "enable an 8s watchdog that force-exits 2 if no deadlock is detected")
	flag.Parse()

	g := &repro.Gossip{Closed: true}

	done := make(chan struct{})
	go func() {
		repro.Bootstrap(g, false) // buggy: leaks the lock on break
		close(done)
	}()

	if *watchdog {
		go func() {
			<-time.After(8 * time.Second)
			fmt.Println("CONFIRMED: gossip.Bootstrap self-deadlock (watchdog)")
			os.Exit(2)
		}()
	}

	<-done // bootstrap returned (it broke while still holding g.Mu in buggy mode)

	// The lock is held by the already-exited bootstrap goroutine and will
	// never be released, so this blocks the only remaining goroutine.
	// Go's native deadlock detector then fires with exit code 2.
	g.Mu.Lock()
	g.Mu.Unlock()
	fmt.Println("returned (this line should never print in buggy mode)")
}
