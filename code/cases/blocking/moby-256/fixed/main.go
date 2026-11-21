// docker#256 修复版 —— 把 stderr 的读取挪到独立 goroutine，两个管道同时被消费。
//
// 对应上游补丁 58befe30：stderr 由一个 goroutine 读进 errChan，
// 读 stdout 的 goroutine 在 copy 结束后从 errChan 取 errText，再 Wait。
// 子进程永远不会因为 stderr 写满而阻塞。
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
	errChan := make(chan []byte)
	go func() {
		errText, e := io.ReadAll(stderr) // 与 stdout 并行消费
		if e != nil {
			errText = []byte("(couldn't fetch stderr)")
		}
		errChan <- errText
	}()
	go func() {
		_, err := io.Copy(pipeW, stdout)
		if err != nil {
			pipeW.CloseWithError(err)
		}
		errText := <-errChan
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
	for i := 0; i < 16; i++ {
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
			fmt.Println("VERDICT: OK")
			fmt.Println("stream error:", err)
			return
		}
		fmt.Println("VERDICT: OK")
	case <-time.After(5 * time.Second):
		fmt.Println("VERDICT: DEADLOCK")
		os.Exit(2)
	}
}
