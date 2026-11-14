# etcd `etcd#4997` — non-blocking data race on `consistentIndex`

A source-faithful minimal reproduction of a **non-blocking** concurrency bug
from *Understanding Real-World Concurrency Bugs in Go* (Tu, Liu, Song, Zhang;
ASPLOS'19), dataset `non-blocking-bugs/etcd/`.

| Item | Value |
|---|---|
| Dataset row | `bug table.xlsx`, sheet `non-blocking`, BugID **`etcd#4997`** |
| Fix commit | **`4d2d2cabb9b0dcaa16ffd17e6d53a745740f3468`** ("etcdserver: fix race on consistent index", 2016-04-07) |
| Upstream file | `etcdserver/consistent_index.go` |
| Paper category | non-blocking / shared memory / traditional; fix strategy `atomic-patch` (`eliminate shared variable` via atomics), patch size 2 |
| Root cause | `consistentIndex` (a `uint64`) is written by `setConsistentIndex()` and read by `ConsistentIndex()` with **plain loads/stores and no synchronization** → data race |
| Official fix | Route both accessors through `sync/atomic`: `atomic.StoreUint64` / `atomic.LoadUint64` |

## Why this is NON-blocking (and how that differs from the `blocking bugs/` set)

A blocking bug stops progress (deadlock / hang); Go's runtime can emit
`fatal error: all goroutines are asleep - deadlock!` (exit 2). This bug is the
opposite:

- **Nothing ever blocks.** `buggy/main.go` always runs to completion and exits 0.
- The fault is a **data race** — unsynchronized concurrent read/write of a shared
  `uint64` — which is *silent* without instrumentation. It is only observable
  via the **Go race detector** (`go build -race` → `WARNING: DATA RACE`, exit 66).
- Consequence: the verdict is based on a **detector report**, not on a hang or
  exit code. This is the key methodological difference from the deadlock
  reproductions in `../../blocking bugs/`.

## Source faithfulness

- `buggy/main.go` and `fixed/main.go` are minimal extractions of the real
  upstream code (type + two accessors + a one-writer/one-reader driver). They
  are byte-identical to each other except for the exact upstream fix; running
  `diff buggy/main.go fixed/main.go` reproduces the patch (adding
  `sync/atomic` and replacing the plain load/store with atomic ones).
- The verbatim upstream commit + diff is saved in
  `results/real-source-evidence/etcd_consistent_index_4d2d2cab.fix.txt`.
- A representative full race-detector stack is in
  `results/real-source-evidence/sample_race_report.log` — it points exactly at
  `setConsistentIndex()` (write) and `ConsistentIndex()` (read).

## Go toolchain choice (two Go versions configured in WSL/Linux)

Both toolchains build the **same** source files:

| Toolchain | Version | Role |
|---|---|---|
| `go` (default) | **Go 1.26.8** linux/amd64 | Primary: modern, reliable `-race`, module-aware |
| `$HOME/sdks/go1.8.7/bin/go` (with `GOROOT`, `GO111MODULE=off`) | **Go 1.8.7** linux/amd64 | Era-faithful cross-check: closest to the 2016 upstream commit; proves the race and the fix are not artifacts of a modern runtime |

Both were verified to detect a `WARNING: DATA RACE` (exit 66) on a control
program before the experiment. `atomic.LoadUint64`/`StoreUint64` and the race
detector work on both. Environment details:
`results/real-source-evidence/ENVIRONMENT.txt`.

## Results (Linux / WSL2, 20 runs per group)

Build: `go build -race` (and a plain build without `-race`), one writer +
one reader started together, 5000 iterations each, `GORACE=halt_on_error=1`.

| Toolchain | Mode | Build | `WARNING: DATA RACE` | Exit |
|---|---|---|---|---|
| Go 1.26.8 | buggy | `-race` | **20/20** | 66 |
| Go 1.26.8 | fixed | `-race` | 0/20 | 0 |
| Go 1.26.8 | buggy | plain | 0/20 (silent, no deadlock) | 0 |
| Go 1.26.8 | fixed | plain | 0/20 | 0 |
| Go 1.8.7 | buggy | `-race` | **20/20** | 66 |
| Go 1.8.7 | fixed | `-race` | 0/20 | 0 |

- Raw per-run logs + `statistics.csv`: `results/raw/`
- Chart: `results/figures/race_detection_summary.svg`
- Full detector stack: `results/real-source-evidence/sample_race_report.log`

## How to reproduce

```bash
# Linux / WSL2 with a Go toolchain
bash scripts/run_experiments.sh          # full 20x matrix, both toolchains

# or by hand:
go build -race -o /tmp/buggy buggy/main.go
GORACE=halt_on_error=1 /tmp/buggy -n 5000     # WARNING: DATA RACE, exit 66
go build -race -o /tmp/fixed fixed/main.go
/tmp/fixed -n 5000                             # clean, exit 0
go build -o /tmp/buggy_plain buggy/main.go
/tmp/buggy_plain -n 5000                       # completes normally: NON-blocking
```

## Honest deviations / limitations (reduced-scale)

- **D1 (reduced scale).** Mechanism-level minimal reproduction, not a build of
  etcd itself (which needs a large dependency tree). The shared `uint64`, the
  two accessors, and the missing/extra atomicity are faithful; the surrounding
  raft/etcdserver machinery is not modeled.
- **D2 (trigger).** Upstream the race is between `setConsistentIndex()` (called
  while applying raft entries) and `ConsistentIndex()` (called by the watchable
  KV). We drive exactly these two methods concurrently to make the race
  deterministic.
- **D3 (no observed corruption).** We claim "the race exists and the official
  fix removes it", not that a torn/misordered read was observed in practice.
  On amd64 a plain `uint64` load/store often happens to be atomic in hardware,
  which is exactly why such bugs are silent; the Go memory model still forbids it.
- **D4 (detector, not runtime hang).** Verdict = race-detector report, not a
  deadlock/hang. There is deliberately **no** `all goroutines are asleep` signal.
- **D5 (iteration count).** 5000 iterations/goroutine and 20 repeats are chosen
  for a stable 20/20 detection rate; a single run already reports the race.
- **D6 (paths).** Race-detector stacks in the logs contain absolute paths of the
  machine that ran them; line numbers refer to `buggy/main.go`, not to the
  upstream file.

Relation to the rest of the submission: this folder lives under
`1240012684/non-blocking bugs/` and complements the six blocking (deadlock)
reproductions under `1240012684/blocking bugs/`, so that both bug categories of
the paper (Section 5 blocking / Section 6 non-blocking) are covered.
