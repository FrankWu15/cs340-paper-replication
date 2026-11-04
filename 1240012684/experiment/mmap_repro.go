package main

import (
	"fmt"
	"os"
	"runtime/pprof"
	"sync"
	"sync/atomic"
	"time"

	bolt "github.com/boltdb/bolt"
)

const (
	readerCount = 16
	writeCount  = 1200
	valueSize   = 64 * 1024
	timeout     = 120 * time.Second
)

func main() {
	dbPath := "./mmap-repro.db"
	_ = os.Remove(dbPath)

	db, err := bolt.Open(dbPath, 0600)
	if err != nil {
		fmt.Println("open database:", err)
		os.Exit(1)
	}

	fmt.Println("Database opened.")
	fmt.Printf("Readers: %d, Writes: %d, Value size: %d KB\n",
		readerCount, writeCount, valueSize/1024)

	var readCount int64
	var writeDone int32
	var wg sync.WaitGroup

	start := make(chan struct{})

	// Start concurrent read-only transactions.
	for i := 0; i < readerCount; i++ {
		wg.Add(1)

		go func(id int) {
			defer wg.Done()
			<-start

			for atomic.LoadInt32(&writeDone) == 0 {
				tx, err := db.Begin(false)
				if err != nil {
					fmt.Printf("reader %d Begin error: %v\n", id, err)
					return
				}

				b := tx.Bucket([]byte("data"))
				if b != nil {
					_ = b.Get([]byte("key-00000000"))
				}

				// Keep the read transaction alive briefly.
				time.Sleep(2 * time.Millisecond)

				if err := tx.Rollback(); err != nil {
					fmt.Printf("reader %d Rollback error: %v\n", id, err)
					return
				}

				atomic.AddInt64(&readCount, 1)
			}
		}(i)
	}

	// Start the writer.
	wg.Add(1)
	go func() {
		defer wg.Done()
		<-start

		value := make([]byte, valueSize)

		for i := 0; i < writeCount; i++ {
			// Make values distinguishable.
			value[0] = byte(i % 256)

			err := db.Update(func(tx *bolt.Tx) error {
				b, err := tx.CreateBucketIfNotExists([]byte("data"))
				if err != nil {
					return err
				}

				key := []byte(fmt.Sprintf("key-%08d", i))
				return b.Put(key, value)
			})

			if err != nil {
				fmt.Println("writer error:", err)
				break
			}

			if (i+1)%100 == 0 {
				info, _ := os.Stat(dbPath)
				if info != nil {
					fmt.Printf("writer: %d/%d, database size: %.2f MB\n",
						i+1, writeCount,
						float64(info.Size())/(1024*1024))
				}
			}
		}

		atomic.StoreInt32(&writeDone, 1)
	}()

	fmt.Println("Starting concurrent workload...")
	close(start)

	finished := make(chan struct{})
	go func() {
		wg.Wait()
		close(finished)
	}()

	select {
	case <-finished:
		fmt.Println("\nWorkload completed.")
		fmt.Printf("Read transactions completed: %d\n",
			atomic.LoadInt64(&readCount))

		if err := db.Close(); err != nil {
			fmt.Println("close database:", err)
			os.Exit(1)
		}

		fmt.Println("RESULT: COMPLETED")

	case <-time.After(timeout):
		fmt.Println("\nRESULT: TIMEOUT")
		fmt.Println("Goroutine stack dump:")
		_ = pprof.Lookup("goroutine").WriteTo(os.Stdout, 2)
		os.Exit(2)
	}
}
