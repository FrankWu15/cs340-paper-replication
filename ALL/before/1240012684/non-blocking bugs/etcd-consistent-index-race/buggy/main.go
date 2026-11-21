// Reproduction of the NON-BLOCKING data race fixed by etcd commit
// 4d2d2cabb9b0dcaa16ffd17e6d53a745740f3468 ("etcdserver: fix race on
// consistent index", 2016-04-07), in etcdserver/consistent_index.go.
//
// Root cause: `consistentIndex` (a uint64) is written by setConsistentIndex()
// and read by ConsistentIndex() with plain (non-atomic) loads/stores and NO
// synchronization. Concurrent access is a data race. This is a NON-BLOCKING
// bug: nothing deadlocks, the program always finishes, and the fault is
// silent unless the Go race detector (-race) is enabled.
//
// This is a faithful minimal extraction of the BUGGY (pre-fix) source. The
// companion fixed/main.go differs only by the exact upstream fix: routing
// both accessors through sync/atomic (LoadUint64 / StoreUint64).
package main

import (
	"flag"
	"fmt"
	"sync"
)

// consistentIndex mirrors upstream etcdserver.consistentIndex (uint64).
type consistentIndex uint64

func (i *consistentIndex) setConsistentIndex(v uint64) { *i = consistentIndex(v) }
func (i *consistentIndex) ConsistentIndex() uint64     { return uint64(*i) }

// ---- driver: one writer + one reader, started together, no per-access sync ----
func main() {
	iters := flag.Int("n", 20000, "iterations per goroutine")
	flag.Parse()

	var idx consistentIndex
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(2)

	go func() { // writer: setConsistentIndex
		defer wg.Done()
		<-start
		for i := 0; i < *iters; i++ {
			idx.setConsistentIndex(uint64(i))
		}
	}()
	go func() { // reader: ConsistentIndex
		defer wg.Done()
		<-start
		for i := 0; i < *iters; i++ {
			_ = idx.ConsistentIndex()
		}
	}()

	close(start)
	wg.Wait()
	fmt.Println("completed without deadlock (data race is silent unless -race is on)")
}
