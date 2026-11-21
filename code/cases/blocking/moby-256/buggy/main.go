// docker#256 —— 先读 stdout 再读 stderr，子进程写满 stderr 的管道缓冲后双方互等。
//
// 原代码 archive.go 的 CmdStream：同一个 goroutine 里先 io.Copy(pipeW, stdout)，
// 等 stdout 到 EOF，之后才 io.ReadAll(stderr)。子进程一旦先往 stderr 写超过
// 管道缓冲（Linux 64KB）就会被阻塞、不退出；而 stdout 也不会 EOF。经典的双向管道死锁。
//
// 复现方式：本程序以 -child 启动自身作为子进程，子进程先写 1MB 到 stderr，
// 再写 stdout。父进程按原顺序读，必然卡死。
package main

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"time"
)

// CmdStream 与上游同结构：先 copy stdout，再读 stderr，最后 Wait。
func CmdStream(cmd *exec.Cmd) (io.Reader, error) {
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}

	pipeR, pipeW := io.Pipe()
	go func() {
		_, err := io.Copy(pipeW, stdout) // ← 等 stdout EOF
		if err != nil {
			pipeW.CloseWithError(err)
		}
		errText, e := io.ReadAll(stderr) // ← 这之后才读 stderr
		if e != nil {
			errText = []byte("(couldn't fetch stderr)")
		}
		if err := cmd.Wait(); err != nil {
			pipeW.CloseWithError(errors.New(err.Error() + ": " + string(errText)))
		} else {
			pipeW.Close()
		}
	}()
	return pipeR, nil
}

func child() {
	buf := bytes.Repeat([]byte("e"), 64*1024)
	for i := 0; i < 16; i++ { // 1MB，远超管道缓冲
		os.Stderr.Write(buf)
	}
	fmt.Fprintln(os.Stdout, "hello")
	os.Exit(0)
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "-child" {
		child()
		return
	}

	self, _ := os.Executable()
	cmd := exec.Command(self, "-child")
	out, err := CmdStream(cmd)
	if err != nil {
		fmt.Println("start failed:", err)
		os.Exit(1)
	}

	done := make(chan error, 1)
	go func() {
		_, err := io.Copy(io.Discard, out)
		done <- err
	}()

	select {
	case err := <-done:
		if err != nil {
			fmt.Println("VERDICT: OK") // 有错误但流已读完，不算死锁
			fmt.Println("stream error:", err)
			return
		}
		fmt.Println("VERDICT: OK")
	case <-time.After(5 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		fmt.Println("CmdStream 5s 未读完：子进程卡在 stderr 写入，父进程卡在等 stdout EOF")
		os.Exit(2)
	}
}
