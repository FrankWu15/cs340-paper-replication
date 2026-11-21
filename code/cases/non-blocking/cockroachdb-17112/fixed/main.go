// cockroachdb#17112 修复版 —— 持有锁时就把文件列表拷进 checkpointFiles，
// 锁外只用这份快照，拷贝长度恒等于决策时刻的长度。
package main

import (
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

const checkpointInterval = time.Microsecond

type backupState struct {
	mu             sync.Mutex
	files          []string
	lastCheckpoint time.Time
}

func (s *backupState) exportFile(name string) {
	s.mu.Lock()
	s.files = append(s.files, name)
	s.mu.Unlock()
}

// checkpoint 对应补丁后的实现。
func (s *backupState) checkpoint(violations *int64) {
	s.mu.Lock()
	var checkpointFiles []string
	lenAtDecision := len(s.files)
	if time.Since(s.lastCheckpoint) > checkpointInterval {
		s.lastCheckpoint = time.Now()
		checkpointFiles = append([]string(nil), s.files...) // 锁内拷贝
	}
	s.mu.Unlock()

	if checkpointFiles == nil {
		return
	}

	_ = fmt.Sprintf("job-%d", 1)

	if len(checkpointFiles) != lenAtDecision {
		atomic.AddInt64(violations, 1)
	}
}

func main() {
	s := &backupState{lastCheckpoint: time.Now()}
	var violations int64

	for w := 0; w < 8; w++ {
		go func(id int) {
			for i := 0; ; i++ {
				s.exportFile(fmt.Sprintf("file-%d-%d", id, i))
			}
		}(w)
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		s.checkpoint(&violations)
	}

	s.mu.Lock()
	n := len(s.files)
	s.mu.Unlock()

	if violations > 0 {
		fmt.Println("VERDICT: BUG")
		fmt.Printf("快照与决策时刻不一致 %d 次\n", violations)
		os.Exit(3)
	}
	fmt.Printf("VERDICT: OK\nfiles=%d\n", n)
}
