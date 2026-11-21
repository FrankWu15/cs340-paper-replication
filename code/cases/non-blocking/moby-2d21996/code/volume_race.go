package main

import (
	"fmt"
	"os"
	"sync"
)

type volumeCounter struct {
	count int
}

type volumeStore struct {
	vols map[string]*volumeCounter
	mu   sync.Mutex
}

func (s *volumeStore) Count(name string, fixed bool) int {
	if fixed {
		s.mu.Lock()
		defer s.mu.Unlock()
	}

	vc, exists := s.vols[name]
	if !exists {
		return 0
	}
	return vc.count
}

func (s *volumeStore) List(fixed bool) int {
	if fixed {
		s.mu.Lock()
		defer s.mu.Unlock()
	}

	count := 0
	for range s.vols {
		count++
	}
	return count
}

func (s *volumeStore) Increment(name string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if vc, exists := s.vols[name]; exists {
		vc.count++
		return
	}
	s.vols[name] = &volumeCounter{count: 1}
}

func main() {
	if len(os.Args) != 3 {
		fmt.Println("Usage: go run -race volume_race.go <count|list> <before|after>")
		return
	}

	mode := os.Args[1]
	fixed := os.Args[2] == "after"

	if os.Args[2] != "before" && os.Args[2] != "after" {
		fmt.Println("Version must be before or after")
		return
	}

	store := &volumeStore{
		vols: map[string]*volumeCounter{
			"volume-0": {count: 0},
		},
	}

	var wg sync.WaitGroup
	start := make(chan struct{})

	wg.Add(2)

	go func() {
		defer wg.Done()
		<-start

		for i := 0; i < 10000; i++ {
			store.Increment("volume-0")
			if mode == "list" {
				store.Increment(fmt.Sprintf("volume-%d", i+1))
			}
		}
	}()

	go func() {
		defer wg.Done()
		<-start

		for i := 0; i < 10000; i++ {
			switch mode {
			case "count":
				store.Count("volume-0", fixed)
			case "list":
				store.List(fixed)
			default:
				fmt.Println("Mode must be count or list")
				return
			}
		}
	}()

	close(start)
	wg.Wait()

	fmt.Println("Test completed")
}
