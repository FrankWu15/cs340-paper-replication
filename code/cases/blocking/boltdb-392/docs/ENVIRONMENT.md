# Environment and Deviations

## 1. Pinned environment (authoritative for every reported number)

Recorded automatically by `scripts/run_experiments.sh` into
`results/environment.txt` at the start of the final experiment
(UTC 2026-11-05T03:32:07Z).

| Item | Value |
|---|---|
| OS | Ubuntu 26.04 LTS ("Resolute Raccoon") |
| Kernel | `6.18.33.2-microsoft-standard-WSL2` (WSL2, x86_64) |
| CPU | 13th Gen Intel(R) Core(TM) i5-13420H, 12 logical CPUs |
| Memory | 8,183,758,848 bytes (7.6 GiB) |
| Go | `go1.26.8 linux/amd64` |
| C compiler | `gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0` |
| Python | 3.14.4 (stdlib only for the analysis) |
| Git | 2.53.0 |
| `GOMAXPROCS` | unset (runtime default = 12, confirmed in every `[info]` line) |
| `GOTRACEBACK` | `all` (full goroutine dumps in the raw logs) |
| `GOPROXY` / `GOSUMDB` | `off` / `off` (fully offline build from vendored source) |
| BoltDB | commit `2f1ce7a837dcb8da3ec595b1dac9d0632f0f99e8` (tag `v1.3.1`, 2017-07-17) |
| `third_party/bolt/db.go` SHA-256 | `9e6f2835024a04b750ae5a942835d4239c0351f04a452d93b678a50ede1e59d3` |
| `bin/repro` SHA-256 | `f2d99175902ea5a6a25ecb94c4289859aec5308a900a4f59c1b87ef94ddeffdd` |
| Per-mode trials | 10 (assignment requires >= 3) |
| Timeout | 5 s for the main experiment, 15 s for the race check |

The Dockerfile pins `golang:1.26-bookworm`; it was not built on the reporting
machine because the Docker daemon was not running. The verified
reproducibility path is `./setup.sh && make build && make verify && make run`
on the environment above. `setup.sh` can re-fetch the exact BoltDB commit and
verifies the tarball SHA-256
`95dc5842dab55f7519b7002bbec648321277b5d6f0ad59aab509ee59313b6386`.

## 2. Complete deviation table (Table 3 of the report)

| # | Item | Original setting in the paper | Setting used here | Reason |
|---|---|---|---|---|
| D1 | BoltDB revision | The buggy version from the 2015 bug report; no commit hash is given in the paper or in the dataset row (`commit hash` column literally contains `boltdb#392`) | `v1.3.1`, commit `2f1ce7a…` (2017), vendored byte-for-byte | A pinned, publicly verifiable commit is required by the assignment. The relevant locking logic is identical: `beginTx()` takes `mmaplock.RLock()` (db.go:466-475), `db.mmap()` takes `mmaplock.Lock()` (db.go:246), and `allocate()` calls `db.mmap()` on growth (db.go:849). We verified this against the 2015 issue discussion. |
| D2 | Go toolchain | Paper published 2019; the exact Go version used for the detector experiment is not reported | Go 1.26.8 | Only toolchain available on the reporting machine; the detector semantics under test are unchanged, and we re-verify the observable behavior (Section 5.3) directly. |
| D3 | OS / kernel | Not reported | Ubuntu 26.04 / WSL2 kernel 6.18.33.2 | Assignment requires OS and kernel versions to be pinned. |
| D4 | Bug-triggering input | GitHub issue #392's user test case: a long-running `db.View()` and a concurrent `db.Update()`; whether the file grows enough to force a remap is left to chance | 512 x 4 KiB writes (2 MiB) with `Options.InitialMmapSize = 32768`, forcing `allocate() -> mmap() -> mmaplock.Lock()` on every run | The paper states the blocking "can be triggered deterministically in every run"; a forced remap makes that claim testable instead of probabilistic. This changes only the workload, not the library. |
| D5 | Repetitions | 1 run per reproduced bug | 10 independent runs per mode (40 total) | Assignment requires mean +/- standard deviation across at least three runs. |
| D6 | Scale | 21 reproduced blocking bugs in 6 applications | 1 bug (BoltDB#392) in 1 application | Reduced scale is explicitly permitted if stated; stated in Section 1.3 and quantified in Section 4.2. |
| D7 | Metric | Binary "detected / not detected" | Binary outcome plus wall-clock latency and exit code | Enables mean +/- SD and clear figures; the binary outcome remains directly comparable. |
| D8 | Timeout | Not reported (a deadlock is expected to be reported by the runtime) | 5 s (15 s for the race check) | Bounds silent hangs of the extension mode; every timeout is recorded in `summary.csv`. |
| D9 | Race-detector check | Not applied to BoltDB#392 in the paper (Section 6.2 evaluates the race detector on non-blocking bugs) | One supplementary `-race` run with `-gcflags=all=-d=checkptr=0` | Controlled check on detector limitations; needed because BoltDB v1.3.1's unsafe pointer code fails Go 1.26 `checkptr`. The main experiment uses an unmodified build. |
| D10 | Build system | Not applicable (paper used the applications' native builds) | Go modules with a local `replace`, `Makefile`, `setup.sh`, `Dockerfile` | Assignment requires a clean-machine build from the README alone. Only a module declaration was added to the vendored 2017 code; no `.go` file of BoltDB was edited. |

## 3. Workload parameters (pinned in `scripts/run_experiments.sh`)

```
keys = 512, value_bytes = 4096, initial_mmap_size = 32768,
live_ticker_ms = 50, modes = buggy move select live
```

The database file is created with `os.MkdirTemp("", "boltdb392-")` inside the
OS temporary directory, so no absolute path is hard-coded and the mmap never
touches a Windows/drvfs mount when running under WSL2.
