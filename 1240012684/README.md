# Case 01: BoltDB mmap Remapping Deadlock

## 1. Overview

This case study focuses on a concurrency bug in BoltDB related to memory-mapped file remapping.

The bug is discussed in the paper:

**Understanding Real-World Concurrency Bugs in Go**

ASPLOS 2019.

The purpose of this case study is to understand the deadlock mechanism, reproduce the reported behavior, and compare the buggy version with the fixed version.

## 2. Target Bug Information

- **Project:** [BoltDB](https://github.com/boltdb/bolt)
- **Buggy commit:** `01bc9be72f46f0f1978b1f1581440c399b3a7684`
- **Fix commit:** `defdb743cdca840890fea24c3111a7bffe5cc0a3`
- **Fix commit message:** `Fix deadlock on remmap.`

The fix modifies the lock acquisition and release order in `beginTx()` and `removeTx()` in `db.go`.

In particular, the changes involve the interaction between `mmaplock` and `metalock`.

## 3. Repository Structure

```text
case-01/
├── README.md
└── experiments/
    ├── mmap_repro.go
    └── results/
        ├── buggy-mmap-result.txt
        └── fixed-mmap-result.txt
```

## 4. Experimental Environment

- **Operating System:** Ubuntu on WSL2
- **Architecture:** linux/amd64
- **Go Version:** 1.26.8
- **Database:** BoltDB

Both buggy and fixed versions were checked in separate working directories.

## 5. Source Code Analysis

The initial source code analysis identified two important functions:

- `beginTx()`: starts a read-only transaction and acquires the mmap read lock.
- `removeTx()`: removes a read-only transaction and releases the mmap read lock.

The buggy and fixed versions use different lock acquisition and release orders.

These changes are relevant to the interaction between read-only transactions, metadata locking, and mmap remapping.

## 6. Preliminary Experiment

A concurrent read/write stress test was implemented in `experiments/mmap_repro.go`.

### Configuration

| Parameter | Value |
|---|---:|
| Number of reader goroutines | 16 |
| Number of write operations | 1,200 |
| Value size | 64 KB |
| Read transaction hold time | 2 ms |
| Timeout | 120 seconds |

The same workload was executed against both versions.

### Results

Both versions completed the preliminary stress test without timing out.

The detailed outputs are available in:

- `experiments/results/buggy-mmap-result.txt`
- `experiments/results/fixed-mmap-result.txt`

**Important:** The preliminary experiment did not reproduce the target deadlock. These results should be interpreted as baseline concurrency stress-test results, not as a successful reproduction of the reported bug.

## 7. Next Steps

The next stage will focus on identifying the exact concurrency scenario that triggers the mmap remapping deadlock.

A targeted reproduction will then be developed to compare the buggy and fixed versions under the same conditions.
