// cockroachdb#17112 —— checkpoint 在锁内决定"该存了"，却在锁外才去读文件列表，
// 中间被并发 append 插进来，存下的快照与决策时刻的状态不一致。
//
// 原代码 pkg/ccl/sqlccl/backup.go：
//   doCheckpoint := timeutil.Since(mu.lastCheckpoint) > backupCheckpointInterval
//   if doCheckpoint { mu.lastCheckpoint = timeutil.Now() }
//   mu.Unlock()
//   ... jobLogger.JobID() ...
//   if doCheckpoint {
//       desc.Lock()
//       desc.Files = append(backupFileDescriptors(nil), mu.files...)  // ← 锁外读
//   }
// 这就是典型的 check-then-use：决策用的是锁内时刻的 mu.files，
// 真正拷贝时 mu.files 已经被其他导出 goroutine 追加过，
// 于是这份 checkpoint 收录了"下一次才该收录"的文件，快照与决策点脱节。
//
// 补丁 d5a604c9 的做法：持锁期间就把 mu.files 拷进 checkpointFiles，锁外只用这份快照。
//
// 判定：比较"拷贝到的长度"与"决策时刻锁内看到的长度"。
// buggy 会出现 len(snapshot) > lenAtDecision；fixed 恒等。
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

// checkpoint 复刻原实现：锁内只判断与更新时间，锁外才读 files。
func (s *backupState) checkpoint(violations *int64) {
	s.mu.Lock()
	doCheckpoint := time.Since(s.lastCheckpoint) > checkpointInterval
	lenAtDecision := len(s.files)
	if doCheckpoint {
		s.lastCheckpoint = time.Now()
	}
	s.mu.Unlock()

	if !doCheckpoint {
		return
	}

	// 原代码在这个位置有 jobLogger.JobID() 等调用，本身存在时间差；这里保留同等开销
	_ = fmt.Sprintf("job-%d", 1)

	snap := append([]string(nil), s.files...) // ← 锁外读取

	if len(snap) != lenAtDecision {
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
		fmt.Printf("checkpoint 快照与决策时刻不一致 %d 次（决策 %d 个文件，拷贝到更多）\n", violations, n)
		os.Exit(3)
	}
	fmt.Printf("VERDICT: OK\nfiles=%d\n", n)
}
