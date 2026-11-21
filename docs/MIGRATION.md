# 迁移对照：`before/` → `11-14/`

原始材料未删、未改，仍在 `../before/`。本文件记录每一项搬到了哪里，以及哪些没搬、为什么。

> **关于路径写法**：下文的 `before/`、`11-14/` 是本地整理时的相对位置。在仓库里，`11-14/` 的内容
> 就是根目录（`code/ data/ docs/ report/ results/`），合并前的状态（四位成员的学号目录）保留在
> tag `pre-unify-2026-11-14` 上，需要对照随时 `git checkout` 得到。

## 总原则

1. **复现的 bug 按 blocking / non-blocking 分开**，一条 bug 一个自包含目录。
2. 成员的**原工程整体搬**（吴德诚的四个 Go module、朱奕铭的 moby 目录），不拆内部结构——
   它们的 `scripts/`、`internal/`、`go.mod` 之间是相对路径引用，拆开就跑不起来。
3. 成员的**代码与证据分离的产出**（李振炜、许汝轩）并入统一布局：程序进 `code/`、
   补丁进 `patches/`、日志进 `logs/`、截图进 `shots/`。
4. 原目录里的**阶段性说明文档**（如 `2026-11-4-1552/README.md`）不搬：其中的结论已并入
   各 case 的 README 与本目录总表，留着会让同一份数据有两处口径。

## 1240012318 李振炜

| 原路径 | 现路径 |
|---|---|
| `2026-11-4-1552/code/repro/scripts/{00_parse_artifact,00_env_report,01_mine_commits,02_static_metrics,03_compare_paper,06_feasibility,07_audit_bug_table,check_pins}.py` | `code/analysis/` |
| `2026-11-4-1552/code/repro/scripts/{p4_case.sh,p4_deps.sh,p4_grpc_logs.sh,08_repro_boltdb.sh,00_pin_exact.sh,00_setup_repos.sh,_paths.sh}` | `code/harness/`（`p4_case.sh`、`p4_deps.sh` 取 **2026-11-13** 的版本：比 11-04 多了 `P4_EXTRA_ARGS` 与 `P4_DEADLINE_HIT`，`grpc-1850` 依赖后者） |
| `2026-11-4-1552/code/repro/local.env` | `code/harness/local.env`、`code/analysis/local.env`（`_paths.sh` 就近读取） |
| `2026-11-4-1552/code/{run.sh,Makefile}` | `code/harness/` |
| `2026-11-13/code/harness/p4_probe.sh`（本次新增的探针驱动） | `code/harness/p4_probe.sh` |
| `2026-11-4-1552/code/repro/tools/goast/` | `code/tools/goast/` |
| `2026-11-4-1552/code/repro/data/*.csv`、`code/repo.lock.tsv` | `data/` |
| `2026-11-4-1552/report/{p0_repo_pin,p1_limitation,p2_static,p4_feasibility,p4_repro_boltdb}.md` | `report/appendix/` |
| `2026-11-4-1552/results/logs/grpc/grpc793/` | `code/cases/blocking/grpc-793/logs/` |
| `…/grpc1293/` | `code/cases/blocking/grpc-1293/logs/` |
| `…/grpc1424/` | `code/cases/blocking/grpc-1424/logs/` |
| `…/grpc1687/` | `code/cases/non-blocking/grpc-1687/logs/` |
| `2026-11-4-1552/results/logs/boltdb_341_*.log` | `code/cases/non-blocking/boltdb-341/logs/` |
| `2026-11-4-1552/results/logs/boltdb_7fb06_*.log` | `code/cases/non-blocking/boltdb-7fb06fee/logs/` |
| `2026-11-4-1552/results/shots/*.png` | 各 case 的 `shots/`（按文件名对应） |
| `2026-11-13/code/cases/grpc-1459/`、`2026-11-13/results/logs/grpc-1459/` | `code/cases/blocking/grpc-1459/`（`code/` 与 `logs/`） |
| `2026-11-13/code/cases/grpc-1667/`、`…/logs/grpc-1667/` | `code/cases/non-blocking/grpc-1667/` |
| `2026-11-13/code/cases/grpc-1850/`、`…/logs/grpc-1850/` | `code/cases/blocking/grpc-1850/` |

搬入时改了 3 处，都是路径基准的变化：

- 三个 `run.sh` 与一个 `run_loop.sh` 的 `ROOT="$HERE/../../.."` → `../../../..`，因为 case
  多了一层 `blocking/`；
- 三个 case README 里的 `results/logs/<case>/` → `logs/`、`bash code/cases/<case>/run.sh` → `bash run.sh`。

## 1240011357 许汝轩

| 原路径 | 现路径 |
|---|---|
| `code/boltdb/cases/02-close-race/{main.go,README.md}` | `code/cases/non-blocking/boltdb-341/code/`（README 改名 `README-upstream.md`） |
| `code/boltdb/patches/02-close-race.patch` | `code/cases/non-blocking/boltdb-341/patches/` |
| `results/boltdb/b2_*.log` | `code/cases/non-blocking/boltdb-341/logs/` |
| `code/boltdb/cases/03-begin-lock-leak/{main.go,README.md}` | `code/cases/blocking/boltdb-begin-lock-leak/code/` |
| `code/boltdb/patches/03-begin-lock-leak.patch` | `code/cases/blocking/boltdb-begin-lock-leak/patches/` |
| `results/boltdb/b3_*.log` | `code/cases/blocking/boltdb-begin-lock-leak/logs/` |
| `code/grpc-go/cases/01-lbwatcher-leak/case.md` | `code/cases/blocking/grpc-1424/code/xu-case.md` |
| `code/grpc-go/patches/01-lbwatcher-leak.patch` | `code/cases/blocking/grpc-1424/patches/` |
| `code/grpc-go/notes/` | `code/cases/blocking/grpc-1424/notes/` |
| `results/grpc-go/grpc_{buggy,fixed}.log` | `code/cases/blocking/grpc-1424/logs/xu/` |
| `code/boltdb/{setup.sh,run.sh}` | `code/harness/xu_boltdb_{setup,run}.sh`（两条 boltdb case 共用） |
| `report/REPORT.md` | `report/appendix/xu-1357-report.md` |
| `results/summary.csv` | `report/appendix/xu-1357-summary.csv` |

他的 `code/grpc-go/README.md` 与 `code/boltdb/README.md` 没有单独搬：内容与 `case.md`、
`REPORT.md` 重复，目标 case README 已重新写过。

## 1240012557 朱奕铭

| 原路径 | 现路径 |
|---|---|
| `1240012557/`（整个目录：README、`Reproduction code/`、`Screenshot/`、`Source_comparison/`） | `code/cases/blocking/moby-17176/` |

目录内结构保持原样。原 README 里写的 `Docker_moby17176_Experiment/` 是提交时的本地目录名，
不影响内容。

## 1240012684 吴德诚

| 原路径 | 现路径 |
|---|---|
| `blocking bugs/boltdb-extra/` | `code/cases/blocking/boltdb-392/` |
| `blocking bugs/cockroachdb-extra/` | `code/cases/blocking/cockroachdb-1cc69980/` |
| `blocking bugs/etcd-extra/` | `code/cases/blocking/etcd-6873-double-lock/` |
| `blocking bugs/kubernetes-extra/` | `code/cases/blocking/kubernetes-62464-20697/` |
| `non-blocking bugs/etcd-consistent-index-race/` | `code/cases/non-blocking/etcd-4997/` |
| `non-blocking bugs/kubernetes-capabilities-race/` | `code/cases/non-blocking/kubernetes-9926/` |
| `non-blocking bugs/make_figures.py` | `code/cases/non-blocking/make_figures.py` |
| `non-blocking bugs/README.md` | `code/cases/non-blocking/xu-2684-nonblocking-overview.md` |

目录名从 `*-extra` 改成 bug 编号，内部结构与 README 一字未动。原 README 里的
「This directory is submitted as `1240012684/boltdb-extra/`」这类句子指的是旧位置，
以本表为准。`etcd-extra`（含 2 条 bug）与 `kubernetes-extra`（含 2 条）没有拆，
原因见 `code/cases/README.md`。

## 没搬的东西

| 内容 | 原因 |
|---|---|
| `before/README.md` | 组级说明，已复制一份到 `docs/original-group-README.md` 备查；`11-14/README.md` 是新的入口 |
| `1240012318/README.md`、`2026-11-4-1552/README.md`、`2026-11-13/README.md` | 阶段性总述。结论已并入各 case README 与本次总表；这三份之间本身就有重复口径，留着会出现三处数字 |
| `2026-11-13/results/README.md`、`code/cases/README.md` | 上一轮目录的索引，已被 `code/cases/README.md` 与本文件取代 |
| `2026-11-13/results/data/grpc_repro_summary.csv` | 被 `results/data/repro_summary.csv`（19 条）取代 |
| `2026-11-13/code/harness/README.md` | 内容并入 `code/harness/README.md` |
| `1240011357/code/boltdb/README.md`、`code/grpc-go/README.md` | 模块级说明，与 `REPORT.md`、`case.md` 重复；目标 case README 已重写 |
| `1240012684/.gitattributes`、`non-blocking bugs/.gitignore` | 仓库级 git 配置，与复现内容无关 |
| `*.gitkeep` | 上一轮的空目录占位，本次按实际内容重建 |
| `1240012318-rollback-backup-*.tar.gz`、`2026-11-11.zip`、`2026-11-4-*.tar.gz` | 历史备份，不属于交付内容（本就在 `before/` 之外） |
| `_unreproduced-2026-11-13/`（`grpc-1662`、`grpc-639`、`grpc-1803`） | 本轮没构造出触发条件，不算复现成功，不并入 |

## 数量核验

| | `before/` | `11-14/` |
|---|---|---|
| 文件数 | 812 | 见 `find . -type f \| wc -l` |
| 复现成功的 bug | 19 条（分散在 4 人目录里） | 19 条（blocking 13 / non-blocking 6） |
