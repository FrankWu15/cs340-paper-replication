package main

import (
	"fmt"
	"sync"
)

func main() {
	var mu sync.Mutex

	fmt.Println("===== Go Runtime Deadlock Detection =====")

	mu.Lock()
	fmt.Println("Main goroutine acquired the mutex")

	fmt.Println("Attempting to acquire the same mutex again...")
	mu.Lock()

	fmt.Println("This line should never be reached")
}
