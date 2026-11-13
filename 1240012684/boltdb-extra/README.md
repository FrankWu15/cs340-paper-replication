# CS340 Research Paper Replication — BoltDB#392

Reduced-scale reproduction of **Paper 5, "Understanding Real-World Concurrency
Bugs in Go"** (Tu, Liu, Song, Zhang; ASPLOS'19), focused on the blocking bug
**`boltdb#392`** from the course dataset (`go-concurrency-bugs-master`,
`bug table.xlsx`, sheet `blocking`, row 90).

| | |
|---|---|
| Paper | <https://songlh.github.io/paper/go-study.pdf> |
| Dataset | <https://github.com/system-pclub/go-concurrency-bugs> |
| Bug report | <https://github.com/boltdb/bolt/issues/392> |
| Upstream code | `boltdb/bolt` tag `v1.3.1`, commit `2f1ce7a837dcb8da3ec595b1dac9d0632f0f99e8` |
| Final report | `report/report.pdf` (source: `report/report.md`) |

## What is reproduced

The paper's **Table 8 / Section 5.3** states that Go's built-in deadlock
detector reports only 2 of 21 reproduced blocking bugs, and names
**BoltDB#392** as one of them. The dataset row classifies it as
`circular`, `non-traditional`, `message passing`, `mixing lock/wait & channel`,
`channel in critical section`, fixed by a 2-line channel patch. We rebuild
that bug from the original issue's test case and check:

1. the deadlock is triggered deterministically and reported by the runtime;
2. the stack trace really shows a **channel wait ↔ RWMutex** circular wait
   (Table 6 "Chan w/", Figure 7);
3. the two small fixes from Table 7 / Figure 7 remove the deadlock;
4. an extension: one unrelated live goroutine silences the detector.

**Scope (stated explicitly, as the assignment allows reduced scale):**
1 of the paper's 21 reproduced blocking bugs, 1 of 6 applications, 40 trials
plus one race-detector check. We do **not** reproduce the taxonomy over 171
bugs, the primitive-usage study (Section 3.2), the non-blocking-bug study
(Section 6), or the other 20 reproduced blocking bugs.

## Repository context

This directory is submitted as `1240012684/boltdb-extra/` inside the group repository
`FrankWu15/cs340-paper-replication` (team member 吴德诚 / Wu Decheng, student
ID 1240012684). Run Git commands (commit, tag, push) from the **group
repository root**, not from this directory. The other student-ID directories
in the group repository belong to other members and are never modified here.

## Requirements

Any Linux (native, VM, WSL2, or container) with:

- Go >= 1.20 (reported numbers: **Go 1.26.8 linux/amd64**)
- bash, coreutils (`date`, `timeout`, `sha256sum`), gcc, python3, make, git
- No network access needed at build/run time: BoltDB is vendored and
  `GOPROXY=off` is set.

Optional (only to regenerate the PDF): `pip install reportlab svglib`, then
`make report`. On a host without a system `python3`, pass the interpreter:
`make report PYTHON=/path/to/venv/bin/python`. The committed
`report/report.pdf` needs no Python packages to read.

The machine actually used: Ubuntu 26.04 LTS on WSL2, kernel
`6.18.33.2-microsoft-standard-WSL2`, 13th Gen Intel i5-13420H (12 logical
CPUs), 8 GiB RAM, gcc 15.2.0, Python 3.14.4, `GOMAXPROCS=12` (default).
Full pinning and checksums: `results/environment.txt`, `docs/ENVIRONMENT.md`.

## Setup / build / run

```bash
git clone <your-group-repo> boltdb392
cd boltdb392
bash setup.sh       # verifies toolchain; re-fetches pinned BoltDB if missing
make build          # builds bin/repro offline
make verify         # 4 smoke trials, ~4 s
make run            # 10 trials x 4 modes + race check, ~75 s
make report         # regenerates report/report.pdf (needs reportlab + svglib)
```

(`chmod +x setup.sh scripts/*.sh` first if you prefer `./setup.sh`; all
Makefile targets call the scripts through `bash`, so no executable bit is
needed.)

`make run` accepts overrides, e.g. `make run REPEAT=30 TIMEOUT=3s`.
To run the extension or a single trial directly:

```bash
./bin/repro -mode=buggy  -run-id=demo-1   # rc=2, "all goroutines are asleep"
./bin/repro -mode=move   -run-id=demo-2   # rc=0
./bin/repro -mode=select -run-id=demo-3   # rc=0
./bin/repro -mode=live   -run-id=demo-4   # hangs; use: timeout 5s ...
```

### Expected output and runtimes

| Command | Runtime | Expected result |
|---|---|---|
| `make build` | ~2 s | `bin/repro` created, no network |
| `make verify` | ~4 s | `PASS buggy/move/select/live` |
| `make run` | ~75 s | 40 raw logs, `results/summary.csv`, `results/statistics.csv`, 3 SVG figures, `results/race_check.txt` |
| `make report` | ~2 s | `report/report.pdf` |

Per mode (10 trials): `buggy` → exit **2** with
`fatal error: all goroutines are asleep - deadlock!`; `move` / `select` →
exit **0** with `[result] ... status=finished`; `live` → exit **124**
(silent hang killed at the 5 s timeout, no deadlock message).
Measured values are in `results/statistics.csv` and `report/report.pdf`.

## Repository layout

```
Makefile, setup.sh, Dockerfile, .gitignore, go.mod
third_party/bolt/         vendored BoltDB v1.3.1 + LICENSE + UPSTREAM_COMMIT.txt
cmd/repro/main.go         CLI entry point (mode, run-id, workload flags)
internal/harness/         the bug-triggering workload and the two fixes
scripts/
  run_experiments.sh      full experiment + provenance + statistics
  race_check.sh           supplementary -race controlled check
  verify.sh               fast smoke checks
  analyze.py              mean +/- SD, tables, SVG figures (stdlib only)
  make_report.py          builds report/report.pdf (needs reportlab)
results/
  environment.txt         pinned environment + checksums
  summary.csv             one row per trial (the primary raw data)
  statistics.csv          per-mode mean +/- SD
  table_paper_vs_ours.md  numbered Table 1
  table_results.md        numbered Table 2
  figures/*.svg           numbered Figures 1-3
  raw/*.log               41 raw logs (40 trials + race check)
  race_check.txt          race-detector controlled check
report/report.pdf         final English report
docs/ENVIRONMENT.md       environment + deviation table
docs/TRACEABILITY.md      every reported number -> log file
```

All raw logs, statistics and figures are committed on purpose: they are the
evidence chain for the report (assignment: "every reported number can be
traced to the logs in the repository").

## Source, credit and modifications

- Original code: `github.com/boltdb/bolt` (MIT), tag `v1.3.1`, commit
  `2f1ce7a837dcb8da3ec595b1dac9d0632f0f99e8`. License copied verbatim to
  `third_party/bolt/LICENSE`. Its locking logic is **unchanged**
  (SHA-256 of `third_party/bolt/db.go` is in `results/environment.txt`).
- Original dataset: `system-pclub/go-concurrency-bugs` (see its README).
- Original test case: calmh's `boltdb_test.go` gist linked from issue #392.
- Files we added: `go.mod`, `third_party/bolt/go.mod` (module declaration only,
  because the 2017 code predates Go modules), `cmd/repro/main.go`,
  `internal/harness/harness.go`, all `scripts/*`, `Makefile`, `setup.sh`,
  `Dockerfile`, `docs/*`, `report/*`, `results/*`.
- We changed no line of BoltDB's locking code. The deterministic remap is
  forced through the public `Options.InitialMmapSize` and a 2 MiB write
  workload, not by patching the library.

## Git requirements (from the assignment)

The repository is already `git init`-ed locally with all files staged (no
commit yet — the message needs your student ID and full name).
See **`docs/GIT_CHECKLIST.md`** for the exact commit/push commands, the
weekly Sunday schedule, the group-information form and the `v1.0` tag.

- Every commit message must contain the **student ID and full name** of the
  committer; each week needs at least one meaningful commit (checked Sundays
  23:59).
- Tag the final version `v1.0`.
- Every group member must make substantive commits from their own account.
- Before submitting, replace the placeholders in the **Contribution
  Statement** in `report/report.md` / `report/report.pdf` with real names,
  IDs and tasks.
- `.gitignore` excludes `bin/`; no build outputs, DB images, traces >50 MB or
  credentials are committed.

## Known limitations

- The `-race` supplementary check needs `-gcflags=all=-d=checkptr=0`:
  BoltDB v1.3.1 uses unsafe pointer conversions rejected by Go 1.26's
  `checkptr`. The main experiment uses an unmodified build.
- The Dockerfile pins `golang:1.26-bookworm`; it was not built on the
  reporting machine (Docker daemon was not running). The verified path is
  `./setup.sh && make build && make run` on the WSL2 Linux environment above.
- Reduced-scale replication suffers selection bias: we chose one of the two
  bugs the paper says the detector can catch. See Section 4 of the report.
