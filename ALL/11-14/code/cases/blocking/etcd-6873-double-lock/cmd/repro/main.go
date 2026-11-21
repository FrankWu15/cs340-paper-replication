package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	"repro/internal/bugs"
)

// Exit codes: 0 = clean exit (fix works), 2 = runtime deadlock detected
// (bug reproduced). Any hang with no deadlock is killed by the external
// `timeout` wrapper (exit 124).
//
// NOTE: we deliberately do NOT use a time.After() watchdog here. A pending
// timer keeps a goroutine runnable, which would suppress Go's "all goroutines
// are asleep" deadlock detector. Instead the trigger runs in a goroutine and
// main blocks on <-done; if the bug fires, every goroutine is asleep and the
// runtime aborts the whole process with exit code 2.
func main() {
	bug := flag.String("bug", "etcd6873", "etcd6873 | doublelock")
	mode := flag.String("mode", "buggy", "buggy | fixed")
	runID := flag.String("run-id", "manual", "identifier for this run")
	flag.Parse()

	start := time.Now()
	done := make(chan int, 1)

	go func() {
		switch *bug {
		case "etcd6873":
			bugs.Trigger6873(*mode == "fixed")
		case "doublelock":
			bugs.TriggerDoubleLock(*mode == "fixed")
		default:
			fmt.Fprintf(os.Stderr, "unknown bug %q\n", *bug)
			os.Exit(3)
		}
		done <- 0
	}()

	rc := <-done // blocks until the bug either returns or the runtime aborts
	if rc == 0 {
		elapsed := float64(time.Since(start).Microseconds()) / 1000.0
		fmt.Printf("[result] run_id=%s bug=%s mode=%s status=finished exit=0 elapsed_ms=%.2f\n",
			*runID, *bug, *mode, elapsed)
	}
	os.Exit(rc)
}
