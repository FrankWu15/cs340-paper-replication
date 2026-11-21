package main

import (
	"fmt"
	"sync"
	"time"
)

type Container struct {
	mu sync.Mutex
}

// Simulate Docker's internal kill() method.
// It does not acquire the lock again.
func (c *Container) kill() error {
	fmt.Println("  [kill] Executing internal kill without acquiring the lock")
	return nil
}

// Simulate Docker's exported Kill() method.
// It acquires the container state lock.
func (c *Container) Kill() error {
	fmt.Println("  [Kill] Attempting to acquire the state lock")
	c.mu.Lock()
	defer c.mu.Unlock()

	return c.kill()
}

// Simulate Docker's Stop() method.
func (c *Container) Stop(fixed bool) error {
	fmt.Println("  [Stop] Acquiring the state lock")
	c.mu.Lock()
	defer c.mu.Unlock()

	fmt.Println("  [Stop] Simulating container shutdown timeout")

	if fixed {
		// Fixed version: call the internal kill() method directly.
		return c.kill()
	}

	// Original version: Kill() tries to acquire the same lock again.
	return c.Kill()
}

func runCase(name string, fixed bool) {
	fmt.Println("\n======", name, "======")

	c := &Container{}
	done := make(chan error, 1)

	go func() {
		done <- c.Stop(fixed)
	}()

	select {
	case err := <-done:
		if err != nil {
			fmt.Println("Result: Execution failed:", err)
		} else {
			fmt.Println("Result: Completed successfully")
		}
	case <-time.After(2 * time.Second):
		fmt.Println("Result: Operation timed out after 2 seconds (lock blocked)")
	}
}

func main() {
	fmt.Println("===== Docker moby#0d9e543 Minimal Reproduction =====")
	runCase("Before Fix", false)
	runCase("After Fix", true)
}
