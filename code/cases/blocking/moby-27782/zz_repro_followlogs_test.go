package jsonfilelog

// Driver for docker#27782 (fixed by a69a59ff "Decouple removing the fileWatcher
// from reading"). Uses the real JSONFileLogger: records are written through
// l.Log while ReadLogs follows the file, then the consumer stops, which is what
// `docker logs -f` does when the client disconnects.

import (
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/docker/docker/daemon/logger"
)

// The LogWatcher buffer holds 4096 messages, so this many records guarantee the
// reader ends up blocked on a send once the consumer walks away.
const records = 8000

func TestFollowLogsClosedConsumer(t *testing.T) {
	dir, err := ioutil.TempDir("", "jsonlog")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	path := filepath.Join(dir, "probe-json.log")

	l, err := New(logger.Context{ContainerID: "probe", LogPath: path})
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	jl := l.(*JSONFileLogger)

	// Tail=0 makes the reader seek to the end and follow only new records, so
	// every message goes through the select at read.go:291 instead of tailFile.
	watcher := jl.ReadLogs(logger.ReadConfig{Follow: true})

	var stopped int32
	go func() {
		for i := 0; i < records && atomic.LoadInt32(&stopped) == 0; i++ {
			msg := &logger.Message{
				Line:      []byte(fmt.Sprintf("line-%d", i)),
				Timestamp: time.Now(),
				Source:    "stdout",
			}
			if err := l.Log(msg); err != nil {
				return
			}
			time.Sleep(50 * time.Microsecond)
		}
	}()

	select {
	case <-watcher.Msg:
	case <-time.After(5 * time.Second):
		atomic.StoreInt32(&stopped, 1)
		t.Fatal("no first message")
	}
	// From here on nobody drains watcher.Msg, exactly like a disconnected client.
	time.Sleep(2 * time.Second)
	atomic.StoreInt32(&stopped, 1)
	watcher.Close()

	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		time.Sleep(200 * time.Millisecond)
		if blocked := blockedInReadLogs(); blocked != "" {
			fmt.Println("VERDICT: BUG  reader still blocked after the consumer closed")
			fmt.Println("  " + blocked)
			fmt.Println("  daemon/logger/jsonfilelog/read.go:294  logWatcher.Msg <- msg")
			return
		}
		if !stillRunning() {
			fmt.Println("VERDICT: OK  reader returned and the file watcher was removed")
			return
		}
	}
	fmt.Println("VERDICT: BUG  reader never returned after the consumer closed")
	buf := make([]byte, 1<<18)
	n := runtime.Stack(buf, true)
	for _, g := range strings.Split(string(buf[:n]), "\n\n") {
		if strings.Contains(g, "jsonfilelog") {
			lines := strings.Split(g, "\n")
			for i := 0; i < len(lines) && i < 5; i++ {
				fmt.Println("  " + strings.TrimSpace(lines[i]))
			}
			fmt.Println("  ---")
		}
	}
}

// blockedInReadLogs reports the first frame when readLogs or followLogs is stuck
// on a channel send, which is the symptom the upstream fix removes.
func blockedInReadLogs() string {
	buf := make([]byte, 1<<18)
	n := runtime.Stack(buf, true)
	for _, g := range strings.Split(string(buf[:n]), "\n\n") {
		if strings.Contains(g, "jsonfilelog") && strings.Contains(g, "chan send") {
			lines := strings.Split(g, "\n")
			out := strings.TrimSpace(lines[0])
			if len(lines) > 1 {
				out += " | " + strings.TrimSpace(lines[1])
			}
			return out
		}
	}
	return ""
}

func stillRunning() bool {
	buf := make([]byte, 1<<18)
	n := runtime.Stack(buf, true)
	s := string(buf[:n])
	return strings.Contains(s, "jsonfilelog.(*JSONFileLogger).readLogs") ||
		strings.Contains(s, "jsonfilelog.followLogs")
}
