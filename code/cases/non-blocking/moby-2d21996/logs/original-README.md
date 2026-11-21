# Docker Non-blocking Concurrency Bug Reproduction

## 1. Project Overview

This project reproduces a non-blocking concurrency bug in Docker.

- **Project:** [moby/moby](https://github.com/moby/moby)
- **Fix Commit:** `2d21996eec8d3e6100f19fa0d0fa7adad25285ca`
- **Parent Commit:** `59311faaed4e3384fc8da738a57a25f17ae07e05`
- **Commit Message:** `volumes: add synchronization to Count and List`
- **Affected File:** `daemon/volumes.go`

## 2. Bug Description

The `volumeStore` structure maintains a shared map protected by a mutex.

Before the fix, `Count()` and `List()` accessed the shared map without acquiring the mutex.

Other methods, including `Increment()` and `Decrement()`, used the mutex when accessing shared data.

This inconsistent synchronization could cause data races during concurrent execution.

## 3. Root Cause

The root cause was missing synchronization in two read methods.

- `Count()` read the volume map and its usage counter without locking.
- `List()` iterated over the volume map without locking.

Meanwhile, other goroutines could modify the same map while holding the mutex.

## 4. Fix Description

The fix adds mutex protection to both methods:

```go
func (s *volumeStore) Count(v volume.Volume) int {
    s.mu.Lock()
    defer s.mu.Unlock()
    // Original implementation
}

func (s *volumeStore) List() []volume.Volume {
    s.mu.Lock()
    defer s.mu.Unlock()
    // Original implementation
}
```

Both methods now use the same mutex as the write operations.

## 5. Experimental Environment

| Component | Version |
|---|---|
| Operating System | Ubuntu 22.04 |
| Architecture | linux/amd64 |
| Go | go1.18.1 |
| Race Detector | Enabled with `-race` |

## 6. Reproduction Method

A standalone Go program was developed to reproduce the synchronization issue.

The program simulates:

- `Increment()`: updates shared volume data while holding the mutex.
- `Count()`: reads a volume counter.
- `List()`: iterates over the shared volume map.

Two modes are supported:

- `before`: simulates the original methods without read-side locking.
- `after`: simulates the fixed methods with mutex protection.

### 6.1 Build

```bash
cd reproduction_code
go build -race -o volume_race volume_race.go
```

### 6.2 Run Count Tests

```bash
./volume_race count before
./volume_race count after
```

### 6.3 Run List Tests

```bash
./volume_race list before
./volume_race list after
```

## 7. Experimental Results

| Test Case | Before Fix | After Fix |
|---|---|---|
| Count | Data race detected | No data race reported |
| List | Data race and concurrent map iteration/write error | No data race reported |

### Count Before Fix

The Race Detector reported:

```text
WARNING: DATA RACE
Found 1 data race(s).
```

The conflicting operations were:

- Write: `Increment()`
- Read: `Count()`

### List Before Fix

The Race Detector reported a data race.

The Go runtime also reported:

```text
fatal error: concurrent map iteration and map write
```

This occurred because `List()` iterated over the map while `Increment()` added entries.

### After Fix

Both tests completed successfully:

```text
Test completed
```

No data race was reported in either test.

The `List After Fix` test used 10,000 iterations after the initial 100,000-iteration test took too long.

## 8. Conclusion

The experiment demonstrates that inconsistent synchronization of a shared map can lead to data races and concurrent map access errors.

Adding the same mutex protection to `Count()` and `List()` prevents these unsynchronized accesses in the reproduction.

This is a mechanism-level reproduction based on the original Docker source code. It is not a full Docker service reproduction.

## 9. Directory Structure

```text
Docker_volume_2d21996_experiment/
├── README.md
├── reproduction_code/
│   └── volume_race.go
├── source_comparison/
│   ├── volumes_before.go
│   ├── volumes_after.go
│   └── volumes.diff
├── test_results/
│   └── test_summary.txt
└── screenshots/
```

## 10. References

- [Docker Repository](https://github.com/moby/moby)
- [Fix Commit](https://github.com/moby/moby/commit/2d21996eec8d3e6100f19fa0d0fa7adad25285ca)
- [Parent Commit](https://github.com/moby/moby/commit/59311faaed4e3384fc8da738a57a25f17ae07e05)
