# Non-blocking concurrency bugs — k8s & etcd reproductions

Two **non-blocking** Go concurrency bugs reproduced to complement the six
**blocking** (deadlock) reproductions in `../blocking bugs/`. Both come from the
ASPLOS'19 paper *Understanding Real-World Concurrency Bugs in Go* and its
public dataset `system-pclub/go-concurrency-bugs` (`non-blocking-bugs/`).

| Folder | Bug (paper BugID) | Fix commit | Root cause | Official fix |
|---|---|---|---|---|
| `kubernetes-capabilities-race/` | `kubernetes#9926` | `de1f246e…` | unsynchronized read/write of global `capabilities` pointer in `pkg/capabilities/capabilities.go` | add `sync.Mutex` (`lock-patch`) |
| `etcd-consistent-index-race/` | `etcd#4997` | `4d2d2cab…` | plain (non-atomic) read/write of shared `consistentIndex uint64` in `etcdserver/consistent_index.go` | use `sync/atomic` (`atomic-patch`) |

## Why a separate folder / category

The paper splits concurrency bugs into **blocking** (Section 5) and
**non-blocking** (Section 6). My earlier six reproductions were all blocking
deadlocks. These two are non-blocking data races, so they live in their own
folder and use a **different verdict**:

| | Blocking (`../blocking bugs/`) | Non-blocking (here) |
|---|---|---|
| Symptom | goroutines stuck, no progress | program always finishes |
| Signal | `fatal error: all goroutines are asleep - deadlock!` (exit 2) | `WARNING: DATA RACE` from `go build -race` (exit 66) |
| buggy verdict | deadlock detected 20/20 | race reported 20/20 |
| fixed verdict | clean exit 0 | clean, 0/20 races |
| Without a detector | hangs | **silent** — completes normally, bug invisible |

The "plain" (no `-race`) runs in each experiment deliberately demonstrate
that last row: the buggy non-blocking program exits 0 with no deadlock. That is
the defining difference, and it is why these two are *not* deadlock bugs.

## Method (same rigor as the blocking set)

- **Source-faithful**: for each bug, `buggy/main.go` and `fixed/main.go` are
  minimal extractions of the real upstream code; they differ from each other
  only by the exact upstream fix (`diff` = the patch). The verbatim upstream
  commit + diff is kept in each `results/real-source-evidence/`.
- **Reduced-scale** (D1–D6 documented in each sub-README): mechanism-level
  reproduction, not a build of Kubernetes/etcd themselves (huge dependency
  trees). We do not claim data corruption in practice — only that the race
  exists and the official fix removes it.
- **Evidence per bug**: 120 raw per-run logs, `statistics.csv`,
  `race_detection_summary.svg`, a full race-detector stack
  (`sample_race_report.log`), `ENVIRONMENT.txt`, and the upstream fix diff.

## Go toolchain (both versions in WSL/Linux, as configured)

The user's Linux environment has two Go toolchains. Both were used on the
**same source files** so the result is not an artifact of one runtime:

- **Primary — Go 1.26.8** (`go`, module-aware): modern, reliable `-race`.
- **Cross-check — Go 1.8.7** (`$HOME/sdks/go1.8.7/bin/go`, `GOROOT` set,
  `GO111MODULE=off`, GOPATH mode): closest to the 2015/2016 upstream commits.
  Old Go also has a working race detector and `sync/atomic`, so the fix is
  exercised on an era-faithful toolchain too.

Choice rationale: use the modern toolchain as the primary (deterministic,
reproducible `-race`), but re-run on the old one to show the data race and the
fix are genuine and version-independent — a stronger claim than either alone.

## Consolidated results (20 runs per group)

| Toolchain | Group | k8s race | etcd race | Expected |
|---|---|---|---|---|
| Go 1.26.8 | buggy `-race` | **20/20** | **20/20** | bug reproduced |
| Go 1.26.8 | fixed `-race` | 0/20 | 0/20 | fix works |
| Go 1.26.8 | buggy plain | 0/20 (no deadlock) | 0/20 (no deadlock) | silent non-blocking |
| Go 1.26.8 | fixed plain | 0/20 | 0/20 | clean |
| Go 1.8.7 | buggy `-race` | **20/20** | **20/20** | cross-check |
| Go 1.8.7 | fixed `-race` | 0/20 | 0/20 | cross-check |

## Reproduce

```bash
# Linux / WSL2, from this folder
bash kubernetes-capabilities-race/scripts/run_experiments.sh
bash etcd-consistent-index-race/scripts/run_experiments.sh
python3 make_figures.py     # regenerate the SVG charts from statistics.csv
```

Each sub-README has the full table, hand-run commands, and the D1–D6
limitations. This folder is placed at `1240012684/non-blocking bugs/` in the
team repository, parallel to `1240012684/blocking bugs/`.
