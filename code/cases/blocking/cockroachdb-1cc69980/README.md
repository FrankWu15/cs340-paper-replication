# cockroachdb gossip missing-unlock deadlock (commit `1cc69980`)

A reproduction of a **blocking (deadlock) concurrency bug** from cockroachdb,
studied in the ASPLOS'19 paper *Understanding Real-World Concurrency Bugs in Go*
(Paper 5 for CS340). This folder is the `1240012684/cockroachdb-extra`
submission, parallel to `boltdb-extra/`, `kubernetes-extra/`, and `etcd-extra/`.

| Field | Value |
|---|---|
| Project | cockroachdb (`github.com/cockroachdb/cockroach`) |
| Bug category | **Blocking** (deadlock) — cockroachdb has **12** such bugs in the paper |
| Fix commit | `1cc699802557f67d4464de391b7350a527f9f445` |
| File | `gossip/gossip.go` |
| Functions | `(*Gossip).bootstrap()` and `(*Gossip).manage()` |
| Root cause | `g.mu.Lock()` acquired in a loop; on the `g.closed` exit path the loop `break`s **without** releasing the mutex. The fix inserts `g.mu.Unlock()` before the `break`. |
| Paper classification | `blocking-bugs/cockroachdb/1cc699802557f67d4464de391b7350a527f9f445.txt` |

> The pull request message (verbatim from the upstream commit): *"Call g.mu.Unlock()
> before calling break. I haven't written a test case, but I'm guessing some of the
> goroutines might get into deadlock during shutdown."*

---

## 1. Root cause

The (reduced) buggy loop was:

```go
func (g *Gossip) bootstrap() {
    for {
        g.mu.Lock()
        g.parseBootstrapAddresses()
        if g.closed {
            break            // BUG: g.mu is never released here
        }
        ...
    }
}
```

When `g.closed` becomes true while a goroutine is inside the loop, the loop
`break`s **while still holding `g.mu`**. The mutex is therefore leaked; any
later `g.mu.Lock()` — by this goroutine on a subsequent call, by `manage()`, or
by any other caller — blocks forever. Because no goroutine can ever make
progress, the program deadlocks. The fix simply releases the lock before
breaking:

```go
        if g.closed {
            g.mu.Unlock()   // FIX
            break
        }
```

This is a textbook *missing-unlock-on-early-exit* deadlock, and it is
**version-independent** (mutex semantics have not changed across Go releases).

---

## 2. Reproduction design (minimal, source-faithful)

cockroachdb is a Cgo + RocksDB-backed system; building the real `gossip` package
is not feasible in this environment (see D5). We therefore extract **only** the
faulty mutex/loop skeleton — the minimal state machine that exhibits the same
root cause, trigger, and fix behaviour as the real bug.

- `repro/gossip.go` — a reduced `Gossip` struct (`Mu sync.Mutex`, `Closed bool`)
  and `Bootstrap(g, fixed)`, a faithful extraction of the buggy `for` loop.
  `fixed==false` leaks the lock on `break`; `fixed==true` releases it.
- `cmd/buggy/main.go` — drives `Bootstrap(g, false)`, then attempts a second
  `g.Mu.Lock()`. Because the lock was leaked, this blocks the only remaining
  goroutine and **Go's native deadlock detector** prints
  `fatal error: all goroutines are asleep - deadlock!` and exits with code **2**.
  A `-watchdog` flag adds an 8 s fallback that force-exits 2 if the native
  detector were suppressed (see D6).
- `cmd/fixed/main.go` — same driver with `Bootstrap(g, true)`; the lock is
  released, so the program terminates cleanly with exit code **0**.

The mapping between the reproduction and the real code is exact at the level of
the bug: same lock (`mu`), same early-exit pattern (`if closed { break }`),
same missing/added `Unlock()`.

---

## 3. Source-faithful verification

The exact upstream fix is preserved verbatim as evidence:

- `results/real-source-evidence/cockroachdb_gossip_1cc69980.fix.txt`
  — the upstream commit message + unified diff, copied from the paper's
  replication repo
  (`go-concurrency-bugs-master/blocking-bugs/cockroachdb/1cc699802557f67d4464de391b7350a527f9f445.txt`).

A full upstream build/run of the real `gossip` package was intentionally **not**
attempted (see D5); the diff above is the authoritative source-faithful proof
that the minimal reproduction matches the real bug.

---

## 4. Experiment & results (Linux)

Run in **Linux** (WSL2 Ubuntu, Go 1.26.8) via `scripts/run_experiments.sh`,
which builds `bin/buggy` and `bin/fixed` and runs each **20 times**, recording
`exit_code` and `deadlock` per run to `results/raw/statistics.csv`.

| Variant | Runs | Deadlock (exit 2) | Clean (exit 0) |
|---|---|---|---|
| **buggy**  | 20 | **20 / 20** | 0 |
| **fixed**  | 20 | 0 | **20 / 20** |

Representative buggy output (`results/raw/buggy_01.log`):

```
fatal error: all goroutines are asleep - deadlock!

goroutine 1 [sync.Mutex.Lock]:
...
main.main()
	.../cockroachdb-bugs-repro/cmd/buggy/main.go:49 +0x13e
```

Representative fixed output (`results/raw/fixed_01.log`):

```
returned (fixed version exits 0)
```

The aggregate result matches the paper's classification of this bug as a
**blocking** (deadlock) bug: the buggy version always deadlocks, the fixed
version never does.

---

## 5. How to reproduce

```bash
# Linux environment (WSL2 / native Linux), Go >= 1.20
cd cockroachdb-bugs-repro
bash scripts/run_experiments.sh        # builds + runs buggy/fixed 20x each

# or manually:
go run ./cmd/buggy                    # -> deadlock, exit 2
go run ./cmd/buggy -watchdog          # -> 8s watchdog fallback, exit 2
go run ./cmd/fixed                    # -> clean, exit 0
```

Each run's stdout/stderr + exit code is saved under `results/raw/`.

---

## 6. Environment

- **OS:** Linux (WSL2 Ubuntu 26.04) — required because the course/grading
  environment is Linux; the deadlock was confirmed here.
- **Go:** 1.26.8 `linux/amd64` (the module declares `go 1.20`; the bug is
  version-independent).
- No external Go modules are required (standard library only), so the
  reproduction builds offline (`GOPROXY=off`).

---

## 7. Deviations & limitations (honest disclosure)

This is a **reduced-scale minimal reproduction**, consistent with the
`D1–D6` honesty conventions already established for the kubernetes/etcd
submissions in this project.

- **D1 — Minimal, not full-system.** We reproduce the bug with a ~15-line
  standalone program, not the full cockroachdb gossip server. The real bug
  lives inside `gossip/gossip.go`, which pulls in the entire cockroachdb
  stack.
- **D2 — Loop body elided.** `g.parseBootstrapAddresses()` and the rest of the
  loop body are omitted; only the `Lock → if closed { break }` skeleton is kept,
  because that is the *sole* locus of the bug.
- **D3 — Trigger driven directly.** In the reproduction `Closed` is set and
  `Bootstrap` is called directly, rather than reached through cockroachdb's real
  shutdown path. The root cause (leaked mutex on early break) is identical.
- **D4 — Modern Go.** Verified on Go 1.26.8, not the 2015-era toolchain the bug
  was originally found with. Mutex lock/unlock semantics are unchanged, so the
  result is valid.
- **D5 — Upstream build not attempted.** Building real cockroachdb requires
  Cgo + RocksDB and a 2015-era vendored dependency tree that cannot be cleanly
  restored. We therefore rely on (a) the exact upstream fix diff as
  source-faithful evidence and (b) the minimal reproduction for the runtime
  behaviour. This is the same pragmatic stance taken for the etcd/kubernetes
  submissions.
- **D6 — Detector nuance.** The buggy run deadlocks via Go's **native** deadlock
  detector (`all goroutines are asleep - deadlock!`, exit 2) when no pending
  timer is present. A pending `time.After` timer *suppresses* the native
  detector (the runtime waits for the timer to potentially wake a goroutine),
  so the optional `-watchdog` mode uses an 8 s fallback to guarantee exit 2.
  This is the same class of suppression seen with the etcd `net/http`
  netpoller case; in both the watchdog is a belt-and-suspenders confirmation,
  not the primary signal.

---

## 8. Files

```
cockroachdb-bugs-repro/
├── README.md
├── go.mod
├── repro/
│   └── gossip.go                 # reduced Gossip + Bootstrap(buggy/fixed)
├── cmd/
│   ├── buggy/main.go             # deadlocks (native detector, exit 2)
│   └── fixed/main.go             # clean exit 0
├── scripts/
│   └── run_experiments.sh        # build + run 20x each, write statistics.csv
└── results/
    ├── raw/                      # per-run logs (buggy_01..20.log, fixed_01..20.log)
    │   ├── statistics.csv        # variant,run,exit_code,deadlock
    │   └── _run.log              # script summary
    ├── figures/
    │   └── deadlock_summary.svg  # 20/20 buggy deadlock vs 20/20 fixed clean
    └── real-source-evidence/
        └── cockroachdb_gossip_1cc69980.fix.txt   # upstream fix diff (verbatim)
```
