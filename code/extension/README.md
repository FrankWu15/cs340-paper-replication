# Ext-v2 · Does parallelism change whether a bug reproduces — and whether the tool catches it?

> Owner: 吴德诚 / 1240012684 · 2026-11-22 · single-factor controlled experiment · three measurements
> Linux (WSL2, 12 logical cores, Go 1.26.8) · 980 runs · ~20 min
>
> **The five bug sources are read from `code/cases/{blocking,non-blocking}/` — this directory carries no
> duplicate copies** (per `docs/PLACEMENT.md`, a case exists once). Only the driver, analysis, and
> results live here.

## 1. Question

The paper reports reproduction as a binary fact: a bug is either "reproduced" (e.g. `3/3 BUG`) or not, and
Table 12 reports that `-race` detected **10 of 20** non-blocking bugs. Both statements carry a hidden
assumption: *that a bug's observability does not depend on how much parallelism the program runs with.*

We test that assumption directly with one knob: **scheduler parallelism (`GOMAXPROCS`)**.

Three measurements under one question:
- **D1 (trigger rate):** does changing `GOMAXPROCS` change *whether* a bug appears in a given run?
- **D1c (trigger intensity):** once it appears, how much does it misbehave (violations per run)?
- **D2 (detection):** does parallelism also change whether the Go race detector *catches* it?

Q2 matters because the paper's `10/20` is a detection rate whose denominator is never stated in terms of
machine parallelism. If detection itself depends on parallelism, then the number is not a property of the
bug alone.

## 2. Design (only one factor varies)

| item | value |
|---|---|
| independent variable | `GOMAXPROCS` ∈ {1, 2, 4, 8, 12} |
| held constant | same binary, same input, same machine, same time budget, same Go toolchain |
| D1 metric | **trigger rate** = fraction of runs where `VERDICT` ≠ `OK` (with Wilson 95% CI) |
| D1c metric | **intensity** = violations per triggered run (mean over triggered runs only) |
| D2 metric | **detection rate** = fraction of `-race` runs containing `WARNING: DATA RACE` (with Wilson 95% CI) |
| runs / cell | probabilistic cases: 30 · deterministic cases: 12 · `-race`: 30 |
| control | every case's `fixed/` build must show 0 triggers |

Five cases, chosen so that both "sensitive" and "insensitive" mechanisms have representatives:

| case | class | mechanism | why it is here |
|---|---|---|---|
| `cockroachdb-17112` | non-blocking | check-then-use across a lock boundary (timing-window race) | predicted **sensitive**: the window only opens when goroutines truly overlap |
| `moby-28682` | non-blocking | `select` with two ready cases; `ctx.Done` steals the `ready` branch | predicted **insensitive**: it is a coin-flip at selection time, not a timing window |
| `kubernetes-36377` | non-blocking | store returns a shared pointer; reconcile mutates it | control: a deterministic shared-memory violation |
| `moby-8909` | blocking | self-deadlock: hold lock, call a method that re-locks | control: deterministic, must be 10/10 everywhere |
| `kubernetes-30872` | blocking | self-deadlock via `HasSynced` callback re-locking | control: deterministic |

`GOMAXPROCS` is the only knob that changes parallelism **without** changing workload, binary, or hardware:
it caps how many Ps may execute Go code concurrently; physical cores, cache, and I/O are untouched.

## 3. Results

980 runs, 20 min 28 s, WSL2 / 12 logical cores / Go 1.26.8. Full tables in `results/summary.md`,
raw per-run rows in `results/raw_runs.csv`, figure in `results/figures/ext_v2_curves.png`.

### D1 · trigger rate (plain binary)

| case | gp=1 | gp=2 | gp=4 | gp=8 | gp=12 |
|---|---|---|---|---|---|
| `cockroachdb-17112` | **18/30 = 60%** | 30/30 | 30/30 | 30/30 | 30/30 |
| `moby-28682` | 30/30 | 30/30 | 30/30 | 30/30 | 30/30 |
| `kubernetes-36377` | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| `moby-8909` (blocking) | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| `kubernetes-30872` (blocking) | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |

Only the timing-window race changes its *trigger rate*: 60% (Wilson 95% CI 42–75%) at `gp=1`,
100% from `gp=2` on. Everything else is 100% at every level.

### D1c · trigger intensity (violations per triggered run)

| case | gp=1 | gp=2 | gp=4 | gp=8 | gp=12 |
|---|---|---|---|---|---|
| `cockroachdb-17112` | **1.28** | 96.7 | 149.2 | 152.8 | **156.9** |
| `moby-28682` | 101.4 | 100.7 | 100.3 | 99.8 | 100.7 |

This is where parallelism bites hardest: **~123× (1.28 → 156.9)** for the timing-window race,
saturating around 4 P's; the message-passing race is flat (~100) because its strength is a
per-selection coin flip, independent of how many P's run.

### D1b · false-negative risk of the "3 clean runs = not reproduced" heuristic

At `gp=1` the timing-window race is clean in ~40% of runs, so P(3 clean in a row) ≈ **6.4%** —
i.e. the standard 3-run protocol would mislabel this bug "not reproduced" about once in 16 tries
**purely because of the core count**. At `gp≥2` this drops to 0%.

### D2 · race-detector hit rate (`-race` binary) — the new dimension

| case | gp=1 | gp=2 | gp=4 | gp=8 | gp=12 |
|---|---|---|---|---|---|
| `cockroachdb-17112` | 30/30 | 30/30 | 30/30 | 30/30 | 30/30 |
| `kubernetes-36377` | **24/30 = 80%** | 30/30 | 30/30 | 30/30 | 30/30 |
| `moby-28682` | **0/30** | 0/30 | 0/30 | 0/30 | 0/30 |

Two things the earlier one-dimensional study could not see:
1. **The detection rate itself depends on parallelism** — `kubernetes-36377` is caught 80% of the
   time at `gp=1` but 100% from `gp=2`. A "10/20 detected" number therefore has a denominator that
   moves with the machine.
2. **`-race` is blind to message-passing bugs** — `moby-28682` is never caught at any parallelism
   (0/30 everywhere), because the detector instruments memory accesses, not which `select` branch fires.

### Control

Every `fixed/` build: **0/10 triggers** at `gp=1` and `gp=12`. The fixes remove the bug; the sweeps
above measure only the buggy builds.

## 4. What this does and does not show

- It shows **trigger rate and detection rate are functions of parallelism** for timing-window races, and
  are flat for mechanism-locked bugs. Verdicts that report "3/3" without the core count are not comparable.
- It does **not** swap hardware: `GOMAXPROCS` is scheduler parallelism, not a physical core count. We say
  "parallelism", never "on a 4-core machine".
- It covers 3 of the 7 non-blocking cases and none of the 6 apps at production scale. Reduced-scale proxy.

## 5. Reproduce

```bash
cd code/extension
bash scripts/run_ext.sh                # full sweep: 5 cases × 5 levels (~20 min on 12 cores)
python3 scripts/analyze.py             # regenerate results/summary.{csv,md} + figures/*.png
```

A fast smoke test (2 levels, 2-3 runs per cell) without overwriting the committed full results:

```bash
LEVELS="1 12" N_PROB=2 N_DET=1 N_RACE=2 WORK=/tmp/ext_smoke bash scripts/run_ext.sh
```

The driver prints the CSV it writes to `results/raw_runs.csv` (10 columns: case, class, gp, phase,
run, verdict, trig, metric, race_flag, rc); `analyze.py` needs only the Python standard library plus
Pillow for the figure.
