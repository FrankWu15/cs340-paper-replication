# CS340 研究论文复现 · 小组交付

## CS340 Research Paper Replication

澳门科技大学 CS340 课程论文复现项目（2026–2027 学年）
Macau University of Science and Technology, CS340 Research Paper Replication (AY 2026–2027)

复现论文：*Understanding Real-World Concurrency Bugs in Go*（Tu, Liu, Song, Zhang; ASPLOS'19）
数据集：<https://github.com/system-pclub/go-concurrency-bugs>

本仓库只有一套结构：四位成员的产出已合并为统一布局，**复现成功的 19 条 bug 按 blocking / non-blocking 分两类，
一条一个自包含目录**。往哪个目录放文件，见 [docs/PLACEMENT.md](docs/PLACEMENT.md)；旧材料搬到哪去了，
见 [docs/MIGRATION.md](docs/MIGRATION.md)。

## 组员 / Team Members

| GitHub | 姓名 Name | 学号 Student ID |
|---|---|---|
| FrankWu15 | 吴德诚 Wu Decheng | 1240012684 |
| DreamingZhu111 | 朱奕铭 Zhu Yiming | 1240012557 |
| icecream1293 | 李振炜 Li Zhenwei | 1240012318 |
| Semliii | 许汝轩 Xu Ruxuan | 1240011357 |

## 复现论文 / Selected Paper

- **论文 / Title**: Understanding Real-World Concurrency Bugs in Go (ASPLOS 2019)
- **作者 / Authors**: Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang
- **论文链接 / Paper**: <https://songlh.github.io/paper/go-study.pdf>
- **官方代码 / Artifacts**: <https://github.com/system-pclub/go-concurrency-bugs>

## 时间节点 / Milestones

- 组队截止 Team formation: 2026-10-25
- 换论文截止 Paper change deadline: 2026-11-01
- 最终答辩 Final presentation: 2026-12-01
- 每周 commit 检查 Weekly TA check: 每周日 23:59 / Every Sunday 23:59

## 协作约定 / Commit convention

课程按周检查每个人的实质性提交，**commit message 必须带学号 + 姓名**，否则该周的贡献无法认定。

Each commit message ends with a signature line:

```
Student: 1240012318 李振炜 (Li Zhenwei)
```

One-time setup per clone (use the email bound to your own GitHub account, so the commit links
to your profile):

```bash
git config user.name  "<你的姓名拼音>"
git config user.email "<你 GitHub 账号绑定的邮箱>"
```

Branching: work on `main` is fine for this size of project. Rebase before pushing if the
remote has moved; do not force-push a commit that someone else has built on.

## 目录 / Layout

```
.
├── code/
│   ├── analysis/        P0–P2 分析脚本（挖提交、AST 静态统计、与论文比对、可行性筛选）
│   ├── harness/         复现驱动（p4_case.sh / p4_probe.sh / p4_deps.sh / 08_repro_boltdb.sh 等）
│   ├── tools/           goast：Go AST 统计工具
│   └── cases/
│       ├── blocking/        blocking bug，一条一个自包含目录（11 个目录 / 13 条）
│       └── non-blocking/    non-blocking bug，一条一个自包含目录（6 个目录 / 6 条）
├── data/                跨 case 的数据：41 条目标、44 条可行性、bug 表、repo.lock.tsv
├── docs/                流程与约定（PLACEMENT.md 放置规则 / MIGRATION.md 搬迁对照）
├── report/              组级报告
│   ├── appendix/        P0/P1/P2/P4 五篇 + 附录
│   └── figures/         跨 case 的汇总图
└── results/
    ├── data/            19 条 bug 的对照总表 repro_summary.csv
    ├── logs/            （空占位）单条 bug 的日志随 case 走，见 code/cases/<类>/<bug>/logs/
    └── shots/           （空占位）截图随 case 走，见 code/cases/<类>/<bug>/shots/
```

**一条 bug 一个自包含目录**是本仓库的关键约定：说明、可运行代码、原始日志、截图都在
`code/cases/<类>/<bug>/` 里。这样既能一条一条单独复跑，也不会出现「代码在 A、证据在 B」的断链。
代价是 `results/logs/` 与 `results/shots/` 不再集中存放——它们保留为占位，见上面的说明。

## 分类原则

| | blocking（论文 §5） | non-blocking（论文 §6） |
|---|---|---|
| 表现 | 进程卡住、不推进 | 进程总能跑完 |
| 典型信号 | `fatal error: all goroutines are asleep - deadlock!`、`go test` 超时 | 不加 `-race` 就静默；加了才有 `WARNING: DATA RACE`，或中途 panic |
| 判据 | buggy 必须卡死、fixed 必须干净通过 | buggy 必须报竞争/崩溃、fixed 必须干净 |
| 常见坑 | 超时不等于 bug——先排除环境导致的 Dial 卡死 | 单跑一次可能抽到「恰好没崩」，必须统计多次 |

## 结果总表（19 条）

| # | bug | 类 | 修复提交 | buggy | fixed |
|---|---|---|---|---|---|
| 1 | boltdb#392 | blocking | — | 死锁 10/10 | 干净退出 |
| 2 | boltdb `defdb743c` | blocking | `defdb743c` | 死锁 | 返回 `ErrDatabaseNotOpen` |
| 3 | cockroachdb `1cc69980` | blocking | `1cc69980` | 死锁 | 干净退出 |
| 4 | etcd#6873 | blocking | `7618fdd1` | 死锁 | 干净退出 |
| 5 | etcd `double-lock` | blocking | `ae062a08` | 死锁 | 干净退出 |
| 6 | grpc#793 | blocking | `5a547ed7` | TIMEOUT ×3 | PASS ×3 |
| 7 | grpc#1293 | blocking | `7df48bee` | FAIL ×3 | PASS ×3 |
| 8 | grpc#1424 | blocking | `4e56696c` | FAIL ×3 | PASS ×3 |
| 9 | grpc#1459 | blocking | `c29d6389` | TIMEOUT ×3 | PASS ×3 |
| 10 | grpc#1850 | blocking | `484b3ebb` | DEADLINE 8/50 | PASS 50/50 |
| 11 | kubernetes#62464 | blocking | `c1b19fce` | 死锁 | 干净退出 |
| 12 | kubernetes#20697 | blocking | `d3639aff` | 死锁 | 干净退出 |
| 13 | moby#17176 | blocking | `2f16895e` | 最小程序超时 | 拿到锁 |
| 14 | boltdb#341 | non-blocking | `c69cb102` | `Commit` 崩溃 | `Close` 阻塞后正常提交 |
| 15 | boltdb `7fb06fee` | non-blocking | `7fb06fee` | 失败率 80~100% | 0~10% |
| 16 | etcd#4997 | non-blocking | `4d2d2cab` | RACE 20/20 | 0/20 |
| 17 | grpc#1667 | non-blocking | `a62701e4` | RACE ×3 | PASS ×3 |
| 18 | grpc#1687 | non-blocking | `c6b46087` | FAIL(panic) ×3 | PASS ×3 |
| 19 | kubernetes#9926 | non-blocking | `de1f246e` | RACE 20/20 | 0/20 |

机器可读版本：`results/data/repro_summary.csv`。逐条的负责人与症状见 `code/cases/README.md`。

## 怎么跑

环境分两套，取决于被测代码的年代：

| 被测对象 | 工具链 | 模式 |
|---|---|---|
| grpc-go（2018 前后） | Go 1.10.8，`GOROOT=/usr/local/go1.10.8` | `GO111MODULE=off`，GOPATH |
| boltdb（2015 前后，许汝轩那套） | Go 1.6.4 | GOPATH |
| moby、吴德诚的四个工程 | Go 1.8~1.26 均可（纯标准库为主） | module |

```bash
# grpc 官方测试类（793 / 1293 / 1424 / 1687）
cd code/cases/blocking/grpc-793 && bash run.sh

# 探针类（1459 / 1667 / 1850）
cd code/cases/blocking/grpc-1459 && bash run.sh 3 30
cd code/cases/blocking/grpc-1850 && bash run_loop.sh 50   # 这条按概率触发，3 次看不出来

# 吴德诚的工程
cd code/cases/blocking/boltdb-392 && bash scripts/run_experiments.sh

# boltdb 两条（李振炜那套）
bash code/harness/08_repro_boltdb.sh
```

`run.sh` 的仓库路径用 `P4_REPO` 覆盖，默认 `$HOME/gopath/src/google.golang.org/grpc`。
判定口径（`PASS`/`FAIL`/`TIMEOUT`/`NOTRUN`/`ERROR`/`DEADLINE`）以 `code/harness/README.md` 为准。

## 已知限制

- **三条没拿下**：`grpc#1662`、`grpc#639`、`grpc#1803` 本轮没构造出触发条件，不在交付范围内。
- **两个目录各含两条 bug**：`etcd-6873-double-lock/`、`kubernetes-62464-20697/`，原因见 `code/cases/README.md`。
- **两条 bug 有两人各自的证据**：`boltdb#341`、`grpc#1424`，两套日志并存、互为交叉验证。
- **部分 case 是机制级最小复现**，不是把 Docker / Kubernetes / etcd 整个跑起来；各 README 里
  都写明了缩比范围，不夸大。
- **阶段性总述未入库**：早期按学号分目录时的几份 README 已并入各 case README 与本文件，
  不再单列，避免同一份数据出现两处口径。
