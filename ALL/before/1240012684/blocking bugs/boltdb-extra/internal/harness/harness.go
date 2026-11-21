// Package harness contains the deterministic workload that triggers
// BoltDB issue #392 (the "Clarify transaction concurrency" deadlock).
//
// The bug: a read-only transaction (DB.View) keeps db.mmaplock.RLock() held
// for the whole duration of its callback.  A concurrent write transaction
// (DB.Update) that has to grow the data file calls db.mmap(), which needs
// db.mmaplock.Lock().  If the read transaction waits on a channel for the
// writer to finish, the two goroutines form a circular wait: the reader
// waits for the writer, and the writer waits for the reader's RLock.
//
// This is the "channel with other primitives" (Chan w/) category of
// Table 6 / Table 8 of Tu et al., ASPLOS'19.  The dataset spreadsheet
// labels boltdb#392 as: circular, non-traditional, message passing,
// "mixing lock/wait & channel", "channel in critical section".
package harness

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"time"

	bolt "github.com/boltdb/bolt"
)

const bucketName = "test"

// Mode values accepted by Run.
const (
	ModeBuggy  = "buggy"  // original bug: channel wait inside the read transaction
	ModeMove   = "move"   // fix: move channel operations out of the critical section
	ModeSelect = "select" // fix: non-blocking select/default (paper Figure 7)
	ModeLive   = "live"   // extension: buggy + one unrelated live goroutine
)

// Config is the complete set of experimental factors.  All of them are
// pinned in scripts/run_experiments.sh so that a run is reproducible.
type Config struct {
	Mode            string
	RunID           string
	Keys            int
	ValueBytes      int
	InitialMmapSize int
	LiveTickerMS    int
}

// Result is printed as a single parseable [result] line on normal exit.
// When the Go runtime deadlock detector fires, the process dies inside
// db.View and no [result] line is produced; the outer shell script records
// the exit status and the runtime's "all goroutines are asleep" message.
type Result struct {
	Mode         string
	RunID        string
	Status       string
	ElapsedMS    float64
	ViewReturned bool
	WriterErr    error
}

type clock struct{ t0 time.Time }

func (c *clock) trace(format string, args ...interface{}) {
	ms := float64(time.Since(c.t0).Microseconds()) / 1000.0
	fmt.Printf("[trace] t_ms=%.3f %s\n", ms, fmt.Sprintf(format, args...))
}

func cleanStaleTempDirs() {
	matches, err := filepath.Glob(filepath.Join(os.TempDir(), "boltdb392-*"))
	if err != nil {
		return
	}
	for _, m := range matches {
		_ = os.RemoveAll(m)
	}
}

// Run executes one replication trial.  It returns normally only for the
// fixed modes (and for the buggy modes if the deadlock somehow does not
// trigger).  All state is local: the database file is created in a fresh
// temporary directory obtained from the OS, and is removed on normal exit.
func Run(cfg Config) (Result, error) {
	res := Result{Mode: cfg.Mode, RunID: cfg.RunID}
	clk := &clock{t0: time.Now()}
	defer func() { res.ElapsedMS = float64(time.Since(clk.t0).Microseconds()) / 1000.0 }()

	fmt.Printf("[info] run_id=%s mode=%s go=%s os=%s arch=%s gomaxprocs=%d\n",
		cfg.RunID, cfg.Mode, runtime.Version(), runtime.GOOS, runtime.GOARCH, runtime.GOMAXPROCS(0))
	fmt.Printf("[info] workload keys=%d value_bytes=%d initial_mmap_size=%d live_ticker_ms=%d\n",
		cfg.Keys, cfg.ValueBytes, cfg.InitialMmapSize, cfg.LiveTickerMS)
	fmt.Printf("[info] lock_map view=mmaplock.RLock writer_growth=mmaplock.Lock (db.mmap)\n")

	cleanStaleTempDirs()
	dir, err := os.MkdirTemp("", "boltdb392-")
	if err != nil {
		return res, err
	}
	defer os.RemoveAll(dir)

	db, err := bolt.Open(filepath.Join(dir, "test.db"), 0644, &bolt.Options{
		InitialMmapSize: cfg.InitialMmapSize,
	})
	if err != nil {
		return res, err
	}
	defer db.Close()

	// Match the bug report: one bucket with one initial value.
	clk.trace("event=db_opened")
	if err := db.Update(func(tx *bolt.Tx) error {
		b, e := tx.CreateBucketIfNotExists([]byte(bucketName))
		if e != nil {
			return e
		}
		return b.Put([]byte("key"), []byte("avalue"))
	}); err != nil {
		return res, err
	}
	clk.trace("event=bucket_ready")

	// Extension factor (single change): one unrelated goroutine that stays
	// runnable via a timer.  It never touches the database or the channels.
	// Section 5.3 of the paper predicts that a still-runnable goroutine is
	// enough to silence Go's built-in deadlock detector.
	if cfg.Mode == ModeLive {
		go func() {
			ticker := time.NewTicker(time.Duration(cfg.LiveTickerMS) * time.Millisecond)
			defer ticker.Stop()
			for range ticker.C {
			}
		}()
		clk.trace("event=live_ticker_started period_ms=%d", cfg.LiveTickerMS)
	}

	start := make(chan struct{})
	done := make(chan struct{})
	errCh := make(chan error, 1)

	go func() {
		<-start
		clk.trace("event=writer_started")
		payload := bytes.Repeat([]byte{0xAB}, cfg.ValueBytes)
		werr := db.Update(func(tx *bolt.Tx) error {
			b := tx.Bucket([]byte(bucketName))
			for i := 0; i < cfg.Keys; i++ {
				if e := b.Put([]byte(fmt.Sprintf("key-%05d", i)), payload); e != nil {
					return e
				}
			}
			return nil
		})
		// Commit/spill is where db.allocate() -> db.mmap() -> mmaplock.Lock()
		// blocks while the read transaction is still open.
		clk.trace("event=writer_returned err=%v", werr)
		errCh <- werr
		close(done)
	}()

	var viewErr error
	switch cfg.Mode {
	case ModeBuggy, ModeLive:
		viewErr = db.View(func(tx *bolt.Tx) error {
			_ = tx.Bucket([]byte(bucketName)).Get([]byte("key"))
			clk.trace("event=view_entered mmaplock=RLock_held")
			start <- struct{}{} // channel op INSIDE the critical section
			clk.trace("event=writer_signalled")
			<-done // BLOCKS inside the critical section -> circular wait
			clk.trace("event=writer_done_observed")
			return nil
		})

	case ModeMove:
		// Fix A (Table 7): move the channel operations out of the critical
		// section.  The read transaction no longer depends on the writer.
		viewErr = db.View(func(tx *bolt.Tx) error {
			_ = tx.Bucket([]byte(bucketName)).Get([]byte("key"))
			clk.trace("event=view_entered mmaplock=RLock_held")
			return nil
		})
		clk.trace("event=view_returned")
		start <- struct{}{}
		<-done // wait OUTSIDE the critical section

	case ModeSelect:
		// Fix B (Figure 7): replace the blocking receive with a
		// select/default so the channel never blocks inside the section.
		viewErr = db.View(func(tx *bolt.Tx) error {
			_ = tx.Bucket([]byte(bucketName)).Get([]byte("key"))
			start <- struct{}{}
			select {
			case <-done:
				clk.trace("event=writer_done_observed")
			default:
				clk.trace("event=default_taken_no_channel_block")
			}
			return nil
		})
		clk.trace("event=view_returned")
		<-done // wait OUTSIDE the critical section

	default:
		return res, fmt.Errorf("unknown mode %q", cfg.Mode)
	}

	if viewErr != nil {
		return res, viewErr
	}
	werr := <-errCh
	clk.trace("event=finished")
	res.Status = "finished"
	res.ViewReturned = true
	res.WriterErr = werr
	res.ElapsedMS = float64(time.Since(clk.t0).Microseconds()) / 1000.0
	fmt.Printf("[result] run_id=%s mode=%s status=finished view_returned=true writer_err=%v elapsed_ms=%.3f\n",
		cfg.RunID, cfg.Mode, werr, res.ElapsedMS)
	if werr != nil {
		return res, werr
	}
	return res, nil
}
