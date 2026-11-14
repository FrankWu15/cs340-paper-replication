# Kubernetes `kubernetes#9926` — non-blocking data race on `capabilities`

A source-faithful minimal reproduction of a **non-blocking** concurrency bug
from *Understanding Real-World Concurrency Bugs in Go* (Tu, Liu, Song, Zhang;
ASPLOS'19), dataset `non-blocking-bugs/kubernetes/`.

| Item | Value |
|---|---|
| Dataset row | `bug table.xlsx`, sheet `non-blocking`, BugID **`kubernetes#9926`** |
| Fix commit | **`de1f246e891fd6794185373f3d3722f80e1048d5`** ("Fix benign data race in pod workers.", 2015-06-16) |
| Upstream file | `pkg/capabilities/capabilities.go` |
| Paper category | non-blocking / shared memory / traditional; fix strategy `lock-patch` (`enforce mutual exclusive`), patch size 5 |
| Root cause | Package-level `capabilities *Capabilities` is written by `SetForTests()` and read by `Get()` with **no synchronization** → data race |
| Official fix | Add a package-level `sync.Mutex` (`var lock sync.Mutex`) and guard both accessors |

## Why this is NON-blocking (and how that differs from the `blocking bugs/` set)

A blocking bug stops progress (deadlock / hang); Go's runtime can emit
`fatal error: all goroutines are asleep - deadlock!` (exit 2). This bug is the
opposite:

- **Nothing ever blocks.** `buggy/main.go` always runs to completion and exits 0.
- The fault is a **data race** — unsynchronized concurrent read/write of a shared
  global — which is *silent* without instrumentation. It is only observable via
  the **Go race detector** (`go build -race` → `WARNING: DATA RACE`, exit 66).
- Consequence: the verdict is based on a **detector report**, not on a hang or
  exit code. This is the key methodological difference from the deadlock
  reproductions in `../../blocking bugs/`.

## Source faithfulness

- `buggy/main.go` and `fixed/main.go` are minimal extractions of the real
  upstream code (globals + accessors + a one-writer/one-reader driver). They are
  byte-identical to each other except for the exact upstream fix; running
  `diff buggy/main.go fixed/main.go` reproduces the patch (adding the mutex and
  the two `Lock`/`defer Unlock` pairs).
- The verbatim upstream commit + diff is saved in
  `results/real-source-evidence/k8s_capabilities_de1f246e.fix.txt`.
- A representative full race-detector stack is in
  `results/real-source-evidence/sample_race_report.log` — it points exactly at
  `Get()` (read) and `SetForTests()` (write).

## Go toolchain choice (two Go versions configured in WSL/Linux)

Both toolchains build the **same** source files:

| Toolchain | Version | Role |
|---|---|---|
| `go` (default) | **Go 1.26.8** linux/amd64 | Primary: modern, reliable `-race`, module-aware |
| `$HOME/sdks/go1.8.7/bin/go` (with `GOROOT`, `GO111MODULE=off`) | **Go 1.8.7** linux/amd64 | Era-faithful cross-check: closest to the 2015 upstream commit; proves the race and the fix are not artifacts of a modern runtime |

Both were verified to detect a `WARNING: DATA RACE` (exit 66) on a control
program before the experiment. Environment details:
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

- **D1 (reduced scale).** This is a mechanism-level minimal reproduction, not a
  build of Kubernetes itself (which needs a large dependency tree). The shared
  variable, the two accessors, and the missing/extra lock are faithful; the
  surrounding kubelet/pod-worker machinery is not modeled.
- **D2 (trigger).** Upstream the race is "benign" and occurs between
  `SetForTests()` (a test helper) and `Get()` in production code. We drive
  exactly these two functions concurrently to make the race deterministic.
- **D3 (benign race).** The upstream commit itself calls this a *benign* data
  race: no crash, no wrong output observed. Our claim is strictly "the race
  exists and the official fix removes it", not "it corrupts data in practice".
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
