# CS340 Research Paper Replication

澳门科技大学 CS340 课程论文复现项目（2026–2027 学年）
Macau University of Science and Technology, CS340 Research Paper Replication (AY 2026–2027)

Course project for **CS340 Operating Systems** (2026–2027).

This repository reproduces the empirical study by Tu, Liu, Song and Zhang on real-world
concurrency bugs in Go programs: how 171 bugs found in six production code bases are
classified, how they can be triggered, and how well Go's built-in detectors find them.

## 组员 / Team Members

| GitHub | 姓名 Name | 学号 Student ID | 分工 Responsibility |
|---|---|---|---|
| FrankWu15 | 吴德诚 Wu Decheng | 1240012684 | *(to be filled)* |
| DreamingZhu111 | 朱奕铭 Zhu Yiming | 1240012557 | *(to be filled)* |
| icecream1293 | 李振炜 Li Zhenwei | 1240012318 | pipeline, environment, static analysis |
| Semliii | 许汝轩 Xu Ruxuan | 1240011357 | *(to be filled)* |

## 复现论文 / Selected Paper

- **论文 Title**: Understanding Real-World Concurrency Bugs in Go (ASPLOS 2019)
- **作者 Authors**: Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang
- **论文 Paper**: <https://songlh.github.io/paper/go-study.pdf>
- **官方代码 Artifacts**: <https://github.com/system-pclub/go-concurrency-bugs>

The upstream artifact is redistributed here under `go-concurrency-bugs-master/` with its
original license and attribution. We claim no authorship over any upstream code.

## 时间节点 / Milestones

- 组队截止 Team formation: 2026-10-25
- 换论文截止 Paper change deadline: 2026-11-01
- 最终答辩 Final presentation: 2026-12-01
- 每周 commit 检查 Weekly TA check: 每周日 23:59 / Every Sunday 23:59

---

## 1. Claims under test

We do not attempt the whole paper. Each claim below maps to one table or figure, and each
will be reported as *supported / partially supported / not supported / inconclusive* in the
final report.

| # | Claim | Paper reference | Status |
|---|-------|-----------------|--------|
| C1 | 171 bugs = 85 blocking + 86 non-blocking; 105 shared-memory + 66 message-passing | Table 2, Table 4 | reproduced (artifact re-derivation) |
| C2 | Blocking bugs are dominated by message-passing causes, not by lock misuse | §5, Fig. 5 | in progress |
| C3 | Go's race detector finds only a minority of non-blocking bugs (10/20), and the deadlock detector only 2/21 blocking bugs | §8, Table 12 | in progress |

C1 is a re-derivation from the authors' published bug table, so agreement alone does not
count as experimental evidence — it is a sanity check that our pipeline reads the artifact
correctly. C2 and C3 are the actual replication targets.

## 2. Repository layout

```
.
├── repo.lock.tsv                 exact upstream commits used (see §4)
├── go-concurrency-bugs-master/   authors' artifact: 169 patches + bug table
├── repro/                        our workbench  (the "code/" + "results/" of the plan)
│   ├── config/apps.yaml          project list, keywords, measurement rules
│   ├── data/                     artifact parsed into CSV (bugs_master.csv, ...)
│   ├── logs/                     pin derivation records, clone logs
│   ├── out/                      generated reports and per-run experiment CSVs
│   ├── scripts/                  pipeline, P0 → P6
│   ├── tools/goast/              Go AST counter for the static primitive tables
│   ├── local.env.example         machine-specific settings template
│   └── README.md                 how to run each stage
├── report/                       final report draft (created at report stage)
└── 6app/                         upstream sources (NOT committed, ~430 MB)
```

Mapping to the directory convention agreed by the team: `code/` = `repro/scripts` +
`repro/tools`, `results/` = `repro/out` + `repro/logs`, `report/` = `report/`. We kept a single
`repro/` root so that every script resolves its inputs and outputs relative to its own
location — the layout can move without editing code, which is what the reproducibility
criterion asks for.

## 3. Environment

| Item | Value |
|---|---|
| Host (pipeline, static analysis) | Windows 11, AMD Ryzen 9 7945HX, 32 GB RAM |
| Guest VM (bug reproduction, detectors) | Ubuntu 18.04.6 LTS, kernel 4.15.0-213, 4 vCPU / 8 GB |
| Go for 2015–2018 code | go1.10.8 linux/amd64 and windows/amd64 |
| Go for tooling | go1.27.3 |
| Python | 3.13 |

Two toolchains are mandatory. The upstream code predates Go modules and vendors its
dependencies; modern Go cannot build most of these repositories at their 2018 commits.
The behaviour of `-race` also differs between releases, so the exact version matters and is
recorded for every measurement.

Ubuntu 18.04 is chosen deliberately: kernel 4.15 still provides cgroup v1 and legacy
iptables, which the 2018 versions of Docker and Kubernetes require. Details and the full
provisioning script are in `repro/Linux环境规格.md` and `repro/scripts/00_provision_linux.sh`.

Machine-specific paths are **not** hardcoded. Defaults are resolved from the repository
layout; anything that differs per machine goes into `repro/local.env`:

```bash
cp repro/local.env.example repro/local.env   # then edit
```

`repro/local.env` is git-ignored on purpose — it holds paths that would not exist on
another machine.

## 4. Pinned upstream commits

Only the artifact is committed; the six large source repositories are not. They are
reproduced exactly by `repo.lock.tsv`:

| Project | Commit | Date | Commits | Paper |
|---|---|---|---|---|
| boltdb | `fd01fc79c553a8e99d512a07e8e0c63d4a3ccfc5` | 2018-03-02 | 816 | 816 |
| etcd | `346589edd1dcb04016594774cef0c0273eeaeb60` | 2018-05-21 | 14101 | 14101 |
| grpc-go | `f66923519395abb416ec5da1ed0db04588a9dfb6` | 2018-05-21 | 2528 | 2528 |
| docker | `9bd5d9912f0cb4fe22b994ac1e7e10038e3be65a` | 2018-05-22 | 35149 | 35149 |
| cockroachdb | `cc4511e1be866da968b94432d7537cf2bba5af3b` | 2018-05-22 | 29485 | 29485 |
| kubernetes | `1f0d9505790c4793d5fbb64bfa20241ff739fc6b` | 2018-05-22 | 65684 | 65684 |

All six match the commit counts reported in the paper exactly. That is not achieved by
picking a date: `--before` is exclusive, so the obvious cut-off overshoots by 3 to 41
commits. `repro/scripts/00_pin_exact.sh` walks back along first-parent from the upper bound
and selects the commit whose `rev-list --count` equals the published number. The derivation
is recorded in `repro/logs/pin_exact.tsv` and explained in `repro/复现方案.md` §P0.

## 5. Build and run

`run.sh` is the entry point; the `Makefile` is a thin wrapper over it, so the same targets
work where `make` is unavailable (stock Windows).

```bash
./run.sh help          # list targets
./run.sh setup-repos   # clone the six repos at the pinned commits (~430 MB, 10-30 min)
./run.sh parse         # artifact -> repro/data/*.csv
./run.sh env-report    # environment + snapshot table -> repro/out/p0_env_report.md
./run.sh goast         # build the Go AST counter into $BIN_DIR/goast
./run.sh check-pins    # verify every repo is at the commit in repo.lock.tsv
./run.sh test          # check pins + re-parse the artifact, fail on first error
```

Expected output and runtime on the reference host:

| Command | Output | Runtime |
|---|---|---|
| `./run.sh parse` | 171 rows, 169 patches matched | ~2 s |
| `./run.sh env-report` | `repro/out/p0_env_report.md` | ~3 s |
| `./run.sh setup-repos` | `6app/` with 6 repositories | ~15 min (network bound) |
| `go build ./cmd/bolt` (Go 1.10.8) | `bolt` binary | 0.4 s |
| `go test -short ./...` (BoltDB) | `ok github.com/boltdb/bolt 9.754s` | ~10 s |

A single bug reproduction (stage P4) takes 30-120 s per configuration, depending on whether
`-race` is enabled; the harness runs each configuration 30 times by default and writes one
CSV row per run so that mean and standard deviation can be recomputed from the log.

## 6. Measured so far

Recorded on 2026-10-26, Windows host, Go 1.10.8 / 1.27.3, unless stated otherwise.

| Measurement | Result |
|---|---|
| BoltDB build at pinned commit | success, 0.4 s |
| BoltDB `go test -short` | pass, 9.754 s |
| BoltDB `go test -short -race` | detector functional; one test fails for timing reasons (see deviation D3) |
| Synthetic data race, 10 runs under `-race` | 10 / 10 detected |
| Unbuffered-channel goroutine leak (`bug.go`), 5 runs under `-race` | 0 / 5 detected |
| Same race, `GOMAXPROCS=1`, 5 runs | result always correct, race still reported every run |
| Same race, `GOMAXPROCS=4`, 5 runs | result wrong 5 / 5, all different |

The last two rows are the basis for our extension experiment: a correct result is not
evidence of the absence of a race, and core count changes the outcome but not detectability.

## 7. Deviations from the paper

Every departure from the original setup is tracked in `repro/复现方案.md` §偏差, with the
original setting, the setting we used, and the reason. Summary:

| # | Item | Paper | Ours | Why |
|---|---|---|---|---|
| D1 | Snapshot acquisition | commit counts only | counts + reconstructed exact commit | makes the code snapshot reproducible |
| D2 | Detection runs | not stated per bug | 100 runs per bug where feasible | detection is probabilistic; one run has no statistical meaning |
| D3 | `-race` test failures | n/a | `TestDB_Open_InitialMmapSize` fails under `-race` | timing assertion, not a data race; excluded from detection statistics |
| D4 | Tooling | not released | `tools/goast` reimplemented | the authors' static analyser is not public |

## 8. Status

- [x] P0 — environment, artifact parsing, six repositories pinned
- [ ] P1 — keyword mining of fix commits (target: 3211 candidates)
- [ ] P2 — static primitive counting (Table 2, Table 4)
- [ ] P3 — dynamic goroutine measurement
- [ ] P4 — bug reproduction (44 targets extracted, 21 blocking / 23 non-blocking)
- [ ] P5 — detector evaluation (race + deadlock)
- [ ] P6 — statistics and figures

## 9. AI usage

Generative AI was used to draft code and documentation in this repository. Every number in
the final report is produced by a script in `repro/scripts/` and traceable to a log file
committed under `repro/out/` or `repro/logs/`; no measurement is reported from a model's
output.
