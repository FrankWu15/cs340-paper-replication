// Reproduction of the NON-BLOCKING data race fixed by Kubernetes commit
// de1f246e891fd6794185373f3d3722f80e1048d5 ("Fix benign data race in pod
// workers", 2015-06-16), in pkg/capabilities/capabilities.go.
//
// Root cause: the package-level `capabilities *Capabilities` is written by
// SetForTests() and read by Get() with NO synchronization. Concurrent calls
// therefore constitute a data race. This is a NON-BLOCKING bug: nothing
// deadlocks, the program always runs to completion, and the fault is silent
// unless the Go race detector (-race) is enabled.
//
// This is a faithful minimal extraction of the BUGGY (pre-fix) source. The
// companion fixed/main.go is identical except for the exact upstream fix
// (a package-level sync.Mutex guarding both accessors); `diff buggy/main.go
// fixed/main.go` therefore equals the upstream patch.
package main

import (
	"flag"
	"fmt"
	"sync"
)

// Capabilities mirrors the upstream pkg/capabilities.Capabilities struct
// (only the fields relevant to the race are kept).
type Capabilities struct {
	AllowPrivileged    bool
	HostNetworkSources []string
}

// ---- faithful buggy globals: no lock ----
var capabilities *Capabilities

func SetForTests(c Capabilities) { capabilities = &c }

func Get() Capabilities {
	if capabilities == nil {
		capabilities = &Capabilities{AllowPrivileged: false}
	}
	return *capabilities
}

// ---- driver: one writer + one reader, started together, no per-access sync ----
func main() {
	iters := flag.Int("n", 20000, "iterations per goroutine")
	flag.Parse()

	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(2)

	go func() { // writer: SetForTests
		defer wg.Done()
		<-start
		for i := 0; i < *iters; i++ {
			SetForTests(Capabilities{AllowPrivileged: i%2 == 0, HostNetworkSources: []string{"loopback"}})
		}
	}()
	go func() { // reader: Get
		defer wg.Done()
		<-start
		for i := 0; i < *iters; i++ {
			_ = Get()
		}
	}()

	close(start)
	wg.Wait()
	fmt.Println("completed without deadlock (data race is silent unless -race is on)")
}
