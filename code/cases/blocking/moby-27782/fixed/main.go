// docker#27782 修复版 —— 用 ctx 统一关闭信号，Remove 交给独立 goroutine，
// 发送侧可被 ctx 打断，不会再卡在"必须送达最后一条"上。
package main

import (
	"bufio"
	"context"
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

type LogWatcher struct {
	Msg     chan Message
	closeCh chan struct{}
}

func NewLogWatcher() *LogWatcher {
	return &LogWatcher{Msg: make(chan Message), closeCh: make(chan struct{})}
}

func (w *LogWatcher) WatchClose() <-chan struct{} { return w.closeCh }
func (w *LogWatcher) Close()                      { close(w.closeCh) }

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

func followLogs(src io.Reader, lw *LogWatcher, fw *FileWatcher, name string) error {
	defer fw.Remove(name)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		select {
		case <-lw.WatchClose():
			fw.Remove(name)
			cancel()
		case <-ctx.Done():
		}
	}()

	dec := bufio.NewReader(src)
	for {
		line, err := dec.ReadString('\n')
		if line != "" {
			msg := Message{Line: strings.TrimRight(line, "\n")}
			select {
			case lw.Msg <- msg:
			case <-ctx.Done():
				return errDone // 关闭时直接退出，不再强行送达
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

	for i := 0; i < 2; i++ {
		<-lw.Msg
	}
	lw.Close()

	select {
	case <-done:
		if fw.Watched("container-json.log") {
			fmt.Println("VERDICT: BUG")
			fmt.Println("fileWatcher 未 Remove")
			os.Exit(3)
		}
		fmt.Println("VERDICT: OK")
	case <-time.After(3 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		os.Exit(2)
	}
}
