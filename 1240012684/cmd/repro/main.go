// Command repro runs one trial of the BoltDB#392 replication.
//
// Usage:
//
//	repro -mode=buggy  -run-id=buggy-01
//	repro -mode=move   -run-id=move-01
//	repro -mode=select -run-id=select-01
//	repro -mode=live   -run-id=live-01
//
// Exit status 0  = the trial finished normally (fixed modes).
// Exit status 2  = Go's built-in deadlock detector fired (buggy mode).
// Exit status 1  = harness/setup error.
// A wall-clock timeout in scripts/run_experiments.sh kills silent hangs.
package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/cs340-replication/boltdb392/internal/harness"
)

func main() {
	mode := flag.String("mode", harness.ModeBuggy,
		"trial mode: buggy | move | select | live")
	runID := flag.String("run-id", "manual-01", "identifier recorded in logs")
	keys := flag.Int("keys", 512, "number of 4 KiB values written by the writer transaction")
	valueBytes := flag.Int("value-bytes", 4096, "size in bytes of each written value")
	mmapSize := flag.Int("initial-mmap-size", 32*1024,
		"BoltDB InitialMmapSize; small on purpose so the writer must remap")
	tickerMS := flag.Int("live-ticker-ms", 50,
		"period of the unrelated live goroutine used only by mode=live")
	flag.Parse()

	cfg := harness.Config{
		Mode:            *mode,
		RunID:           *runID,
		Keys:            *keys,
		ValueBytes:      *valueBytes,
		InitialMmapSize: *mmapSize,
		LiveTickerMS:    *tickerMS,
	}
	_, err := harness.Run(cfg)
	if err != nil {
		fmt.Printf("[result] run_id=%s mode=%s status=error err=%v\n", cfg.RunID, cfg.Mode, err)
		fmt.Fprintln(os.Stderr, "harness error:", err)
		os.Exit(1)
	}
}
