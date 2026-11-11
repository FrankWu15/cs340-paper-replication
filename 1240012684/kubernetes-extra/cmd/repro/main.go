// Command repro runs one trial of a minimal Kubernetes blocking-bug
// reproduction on Linux.
//
// Usage:
//
//	repro -bug=double-rlock -mode=buggy -run-id=double-rlock-buggy-01
//	repro -bug=miss-unlock  -mode=fixed -run-id=miss-unlock-fixed-01
//
// Exit 0 = finished (fixed mode, or any clean completion).
// Exit 2 = Go's built-in deadlock detector fired (expected for buggy mode).
// Exit 1 = harness error.  A wall-clock timeout in run_experiments.sh kills
// silent hangs.
package main

import (
	"flag"
	"fmt"
	"os"
	"runtime"
	"time"

	"k8sbugs/internal/bugs"
)

func main() {
	bug := flag.String("bug", "double-rlock", "bug: double-rlock | miss-unlock")
	mode := flag.String("mode", "buggy", "mode: buggy | fixed")
	runID := flag.String("run-id", "manual-01", "identifier recorded in logs")
	flag.Parse()

	t0 := time.Now()
	trace := func(format string, args ...any) {
		fmt.Printf("[trace] t_ms=%.3f %s\n",
			float64(time.Since(t0).Microseconds())/1000.0, fmt.Sprintf(format, args...))
	}

	fmt.Printf("[info] run_id=%s bug=%s mode=%s go=%s os=%s arch=%s gomaxprocs=%d\n",
		*runID, *bug, *mode, runtime.Version(), runtime.GOOS, runtime.GOARCH,
		runtime.GOMAXPROCS(0))

	var value string
	var err error
	switch *bug {
	case "double-rlock":
		value, err = bugs.RunDoubleRLock(*mode, trace)
	case "miss-unlock":
		value, err = bugs.RunMissUnlock(*mode, trace)
	default:
		fmt.Println("unknown -bug:", *bug)
		os.Exit(1)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "harness error:", err)
		os.Exit(1)
	}

	trace("event=finished")
	fmt.Printf("[result] run_id=%s bug=%s mode=%s status=finished value=%s elapsed_ms=%.3f\n",
		*runID, *bug, *mode, value, float64(time.Since(t0).Microseconds())/1000.0)
}
