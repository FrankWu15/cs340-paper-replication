package docker

// Driver for docker#256 (fixed by 58befe30 "Fix a deadlock in CmdStream").
// archive.go is byte-identical to the upstream file at the tested commit and is
// built on its own with `go test archive.go <this file>`, so CmdStream runs
// unmodified.

import (
	"fmt"
	"io/ioutil"
	"os/exec"
	"testing"
	"time"
)

func TestCmdStreamStderrFlood(t *testing.T) {
	// The child fills the 64 KiB stderr pipe before it ever writes stdout.
	cmd := exec.Command("/bin/sh", "-c", "head -c 1048576 /dev/zero 1>&2; echo done")

	r, err := CmdStream(cmd)
	if err != nil {
		t.Fatal(err)
	}

	done := make(chan string, 1)
	go func() {
		b, err := ioutil.ReadAll(r)
		done <- fmt.Sprintf("%d bytes, err=%v", len(b), err)
	}()

	select {
	case s := <-done:
		fmt.Printf("VERDICT: OK (%s)\n", s)
	case <-time.After(5 * time.Second):
		fmt.Println("VERDICT: DEADLOCK  CmdStream reader did not finish within 5s")
		fmt.Println("  archive.go: inside the goroutine, io.Copy(pipeW, stdout) waits for")
		fmt.Println("  stdout EOF while the child is stuck writing stderr; stderr is only")
		fmt.Println("  read after io.Copy returns")
	}
}
