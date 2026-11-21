// docker#27782 —— 消费者退出后，followLogs 仍要把最后一条消息"送达"，永久阻塞。
//
// 原代码 daemon/logger/jsonfilelog/read.go：followLogs 在多个 select 里监听
// logWatcher.WatchClose()。关闭发生时它走 `case <-logWatcher.WatchClose():` 分支，
// 但该分支里还会执行 `logWatcher.Msg <- msg`（必须送达最后一条），
// 而消费者此时已经不再接收 —— 无缓冲 channel 上永久阻塞。
// 同时 fsnotify 的 fileWatcher.Remove(name) 也只在部分路径被调用，watcher 泄漏。
//
// 补丁 03ea2166... 的做法是引入 ctx：WatchClose 收敛为 ctx.Done()，
// 并在独立 goroutine 里做 Remove + cancel，发送侧改成可被 ctx 打断。
package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"sync"
	"time"
)

var errDone = errors.New("done")

type Message struct{ Line string }

// LogWatcher 对应 logger.LogWatcher：消息通道 + 关闭信号。
type LogWatcher struct {
	Msg     chan Message
	closeCh chan struct{}
}

func NewLogWatcher() *LogWatcher {
	return &LogWatcher{Msg: make(chan Message), closeCh: make(chan struct{})}
}

func (w *LogWatcher) WatchClose() <-chan struct{} { return w.closeCh }
func (w *LogWatcher) Close()                      { close(w.closeCh) }

// FileWatcher 对应 fsnotify 的 watcher，记录还挂着哪些文件。
type FileWatcher struct {
	mu      sync.Mutex
	watched map[string]bool
}

func NewFileWatcher() *FileWatcher {
	return &FileWatcher{watched: map[string]bool{}}
}

func (fw *FileWatcher) Add(name string) {
	fw.mu.Lock()
	defer fw.mu.Unlock()
	fw.watched[name] = true
}

func (fw *FileWatcher) Remove(name string) {
	fw.mu.Lock()
	defer fw.mu.Unlock()
	delete(fw.watched, name)
}

func (fw *FileWatcher) Watched(name string) bool {
	fw.mu.Lock()
	defer fw.mu.Unlock()
	return fw.watched[name]
}

// followLogs 复刻原函数：读到消息就发给消费者；关闭信号到来时仍强行发送最后一条。
func followLogs(src io.Reader, lw *LogWatcher, fw *FileWatcher, name string) error {
	dec := bufio.NewReader(src)
	for {
		line, err := dec.ReadString('\n')
		if line != "" {
			msg := Message{Line: strings.TrimRight(line, "\n")}
			select {
			case lw.Msg <- msg:
			case <-lw.WatchClose():
				lw.Msg <- msg // ← 这里：消费者已走，永久阻塞
				return errDone
			}
		}
		if err != nil {
			if err == io.EOF {
				return errDone
			}
			return err
		}
	}
}

func main() {
	fw := NewFileWatcher()
	fw.Add("container-json.log")
	lw := NewLogWatcher()

	src := strings.NewReader("line1\nline2\nline3\nline4\n")
	done := make(chan error, 1)
	go func() { done <- followLogs(src, lw, fw, "container-json.log") }()

	// 消费者只读两条就断开，并且不再接收任何消息
	for i := 0; i < 2; i++ {
		<-lw.Msg
	}
	lw.Close()

	select {
	case <-done:
		if fw.Watched("container-json.log") {
			fmt.Println("VERDICT: BUG")
			fmt.Println("followLogs 退出但 fileWatcher 未 Remove，watcher 泄漏")
			os.Exit(3)
		}
		fmt.Println("VERDICT: OK")
	case <-time.After(3 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		fmt.Println("followLogs 卡在 Msg <- msg：消费者已断开，无缓冲通道无人接收")
		os.Exit(2)
	}
}
