# etcd Concurrency Bug Reproductions (CS340)

Two blocking concurrency bugs from **"Understanding Real-World Concurrency Bugs
in Go" (Tu et al., ASPLOS'19)**, reproduced and fixed on a clean Linux box.

| Bug | Issue | Type | Fix commit (upstream) | Buggy parent | Real source file |
|---|---|---|---|---|---|
| `etcd#6873` | grpcproxy deadlock on watch-broadcast stop | circular / message passing / channel-in-critical-section / lock+channel | `7618fdd1d642e47cac70c03f637b0fd798a53a6e` | `377f19b0031f9c0aafe2aec28b6f9019311f52f9` | `proxy/grpcproxy/watch_broadcasts.go` |
| double-lock | `httpClusterClient.Sync` self-deadlock | singular / traditional / double-lock | `ae062a0825a4100d0cf9ac7c8bb0fa1ca69c6814` | `83930ac113bf9f30f69ad6cbb33878d75f9684fe` | `client/client.go` |

Both bugs are classified in the paper's `bug table` (blocking sheet): `etcd#6873`
is the same *lock + channel in critical section* family as `boltdb#392`; the
double-lock bug is in the *shared-memory / double-lock* family (same as the
Kubernetes bugs).

## What was reproduced

- `etcd#6873`: in `proxy/grpcproxy/watch_broadcasts.go`, `watchBroadcasts.stop()`
  holds `mu` across `close(updatec)` and a `<-donec` wait, while the coalesce loop
  needs `mu` to finish -> deadlock. The one-line fix (commit `7618fdd1`) moves
  `mu.Unlock()` to just before the `<-donec` wait.
- double-lock: in `client/client.go`, `Sync()` takes `c.Lock()` then calls
  `MembersAPI.List()` -> `Do()` -> `c.RLock()` (inside `Endpoints`/`Do`) ->
  self-deadlock on the same RWMutex. The fix (commit `ae062a08`) moves
  `Lock()` to after `List()` returns.

Both are caught by Go's built-in deadlock detector (`fatal error: all goroutines
are asleep - deadlock!`, exit code 2). The official fixes remove the deadlock
(clean exit 0).

## Source-faithful verification against upstream commits

The minimal reproductions in `internal/bugs/` are **not** hand-written
equivalents — they are faithful transcriptions of the real bugs. To prove this,
we extract the **verbatim** upstream source at the exact commits from the
paper's bug table:

- `scripts/extract_real_source.sh` pulls each bug's real function and its real
  fix diff from a local clone of etcd (`$HOME/etcd-src`, full history) into
  `results/real-source-evidence/` — see `COMMITS.md` and `KEYLINES.txt`.
- `etcd#6873`: real `watchBroadcasts.stop` (buggy `377f19b0`) and the one-line
  fix (commit `7618fdd1`, file `proxy/grpcproxy/watch_broadcasts.go`).
- double-lock: real `httpClusterClient.Sync` / `Do` / `Endpoints` (buggy
  `83930ac1`) and the fix (commit `ae062a08`, file `client/client.go`).

**Real-code compile & run (double-lock).** We extracted the *actual* upstream
`client/client.go` + `client/members.go` from commit `83930ac1` into an
independent Go module (`realcompile/`) and compiled + ran the real
`httpClusterClient.Sync`. It self-deadlocks exactly as the upstream bug
describes; a watchdog confirms the hang with exit code 2 (see
`results/real-source-evidence/realcompile_run.log`):

```
calling REAL httpClusterClient.Sync() from buggy commit 83930ac1 ...
CONFIRMED: real upstream httpClusterClient.Sync self-deadlock
```

The only adaptations to build 2016 code on a modern toolchain are: `context`
from the standard library (was `golang.org/x/net/context`), `http.Transport`
`Dial` -> `DialContext`, and a minimal stub for `pkg/types` (used only by the
unrelated `Add` method). **None of these touch the bug logic.**

`etcd#6873` is verified by source extraction + fix diff only (its bug lives in
`proxy/grpcproxy/watch_broadcasts.go` behind a gRPC dependency chain, so a clean
real-binary compile would require restoring the 2016 vendor tree — see D5).

## Results (20 trials each, Go 1.26.8 / WSL2 Ubuntu 26.04)

| Bug | Mode | Deadlocks detected | Exit | Elapsed (mean ± SD) |
|---|---|---:|---:|---|
| etcd#6873 | buggy | 20/20 | 2 | n/a (deadlock) |
| etcd#6873 | fixed | 0/20 | 0 | 0.86 ± 0.42 ms |
| double-lock | buggy | 20/20 | 2 | n/a (deadlock) |
| double-lock | fixed | 0/20 | 0 | 0.75 ± 0.19 ms |

See `results/statistics.csv`, `results/table_results.md`, and the figures in
`results/figures/` (`figE1_detection_rate.svg`, `figE2_latency.svg`).

## How to reproduce (clean machine)

```bash
# from this directory
pip install matplotlib          # only if you want figures; not needed for the binary
make build                      # builds bin/repro (module mode, Go 1.20+)
make verify                    # 4 smoke trials, ~2 s
make run                       # 20 trials x 2 bugs x 2 modes, ~60 s + figures

# optional: re-extract verbatim upstream evidence (needs ~/etcd-src w/ full history)
bash scripts/extract_real_source.sh
# optional: compile & run the REAL upstream double-lock code (modern Go)
bash scripts/build_and_run_realcompile.sh
```

`make run` writes 80 raw logs to `results/raw/`, a `summary.csv`, statistics,
and the two SVG figures.

## Environment

- Hardware: AMD64 (host), WSL2 guest.
- OS / kernel: Ubuntu 26.04 (WSL2), kernel `6.18.33.2-microsoft-standard-WSL2`.
- Go toolchain: the minimal reproductions build with the host Go (`go1.26.8`).
  The real-code double-lock compile/run (`realcompile/`) also uses the host Go.
  A Go 1.8.7 toolchain was installed earlier from `dl.google.com` (URL + SHA-256
  in `results/environment.txt`) but was **not** required for the verification
  actually performed here.
- No network access is needed at build or run time (all deps vendored or std).

## Deviation from the original (be explicit)

These are **faithful minimal reproductions**, not the full etcd server:

- **D1 — faithful transcription.** `internal/bugs/etcd6873.go` and
  `internal/bugs/etcdDoubleLock.go` transcribe the exact upstream functions
  involved in each bug (and the one-line fix) at the buggy parent commit. The
  lock/goroutine interaction is byte-for-byte the upstream logic; only the
  surrounding production scaffolding (HTTP/gRPC servers, watcher bookkeeping) is
  omitted. `etcd6873.go` mirrors `proxy/grpcproxy/watch_broadcasts.go`'s
  `watchBroadcasts.stop`; `etcdDoubleLock.go` mirrors `client/client.go`'s
  `httpClusterClient.Sync`.
- **D2 — source-faithful evidence.** We extract the *verbatim* upstream source
  and fix diff for both bugs from the real etcd history
  (`scripts/extract_real_source.sh`, `results/real-source-evidence/`), proving
  the transcriptions match the upstream code at the paper's pinned commits.
- **D3 — real upstream code executed (double-lock).** The actual
  `client/client.go` + `client/members.go` from commit `83930ac1` are compiled
  and run; the real `httpClusterClient.Sync` self-deadlocks (exit 2, see
  `realcompile_run.log`). Adaptations: stdlib `context`, `DialContext`, and a
  stub for the unrelated `pkg/types` — none affect the bug.
- **D4 — harness watchdog omitted on purpose.** In `cmd/repro/main.go` the
  trigger runs in a goroutine and main blocks on `<-done` with **no
  `time.After` watchdog**: a pending timer keeps a goroutine runnable and would
  suppress Go's deadlock detector. The external `timeout` wrapper (8 s) bounds a
  false-negative hang (exit 124).
- **D5 — etcd#6873 not compiled as a real binary.** A clean compile of the
  etcd#6873 path needs the 2016 `glide` vendor tree, which is **not** committed
  in those commits and whose 50+ pinned dependencies (golang.org/x/*, grpc, …)
  are not restorable in a modern environment. `scripts/vendor_from_lock.py`
  could not complete. etcd#6873 is therefore verified by source extraction +
  fix diff only; runtime behaviour is shown by the minimal reproduction
  (20/20 deadlocks). This is a declared reduced-scale limitation.
- **D6 — corrected prior claim.** An earlier draft stated that "the upstream
  etcd source compiles with Go 1.8.7 (verified: proxy/grpcproxy builds after
  restoring the vendor tree)". That claim was **not** actually verified and is
  **withdrawn** — see D5.

Paper context: the study reports 85 blocking bugs across 6 applications; this
reproduction covers **2 bugs / 1 application (etcd)** — a reduced scale, declared
up front, as the assignment permits.

## Files

```
cmd/repro/main.go               driver / deadlock-detector harness
internal/bugs/etcd6873.go       etcd#6873 transcription (buggy + fixed)
internal/bugs/etcdDoubleLock.go  double-lock transcription (buggy + fixed)
scripts/run_experiments.sh      20x2x2 batch runner
scripts/verify.sh               4 smoke trials
scripts/analyze.py              statistics + SVG figures (pure stdlib)
scripts/extract_real_source.sh  extract verbatim upstream source + fix diffs
scripts/build_and_run_realcompile.sh  compile & run the REAL upstream double-lock code
scripts/vendor_from_lock.py     restores the pinned etcd vendor tree (attempted, incomplete)
realcompile/                    independent module with the REAL 83930ac1 client code
results/                       raw logs, summary.csv, statistics.csv,
                              table_results.md, figures/, real-source-evidence/
```
