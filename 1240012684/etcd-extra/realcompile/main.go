package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"realetcd/client"
)

func main() {
	cfg := client.Config{
		Endpoints: []string{"http://127.0.0.1:1"},
	}
	c, err := client.New(cfg)
	if err != nil {
		panic(err)
	}
	fmt.Println("calling REAL httpClusterClient.Sync() from buggy commit 83930ac1 ...")

	ctx := context.Background()
	done := make(chan struct{})
	go func() {
		// Real upstream bug: Sync() holds c.Lock() then calls
		// List() -> c.Do() -> c.RLock() on the SAME RWMutex (self-deadlock).
		_ = c.Sync(ctx)
		close(done)
	}()

	select {
	case <-done:
		fmt.Println("returned (this line should never print)")
	case <-time.After(5 * time.Second):
		fmt.Println("CONFIRMED: real upstream httpClusterClient.Sync self-deadlock")
		fmt.Println("(blocked in RLock while holding Lock; Go's native deadlock")
		fmt.Println(" detector does not fire because net/http keeps a netpoller")
		fmt.Println(" goroutine alive, so the scheduler never sees all-asleep)")
		os.Exit(2)
	}
}
