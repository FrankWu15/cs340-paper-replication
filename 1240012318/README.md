# 李振炜 1240012318

CS340 论文复现 —— *Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）

本目录是自己这次作业的全部交付物：可复跑的代码、分析文档、当日归档与证据。

## 目录结构

```text
1240012318/
├── README.md              本文件，入口索引
├── 项目总览.md            项目级说明：做了什么、怎么跑、结论
├── 复现方案.md            方案设计：分几个阶段、每阶段判据
├── run.sh                 总入口，Windows 无 make 也能用
├── Makefile               run.sh 的薄封装
├── repo.lock.tsv          6 个上游仓库的 commit 清单
├── repro/                 活跃代码：脚本、数据、配置
│   ├── scripts/           17 个脚本，按阶段编号
│   ├── data/              解析出来的 CSV 数据表
│   ├── out/               运行产物（报告、静态统计 JSON）
│   ├── logs/              克隆与 pin 记录
│   ├── config/apps.yaml   6 个仓库的元信息
│   └── tools/goast/       Go AST 静态统计器
├── tools/mdtable.py       Markdown 表格按显示宽度对齐的小工具
└── 2026-11-4-1552/        2026-11-04 的只读快照，可整体打包
```

## 两层的关系

`repro/` 是**活跃代码**，改一处就能重跑；`2026-11-4-1552/` 是**当日快照**，
里面带一份当时跑通的脚本副本和全部结果，用于证明某个时间点确实跑出过这个数。
两者脚本内容基本一致，快照那份不再修改。

## 快速开始

```bash
cd 1240012318
./run.sh help            # 看所有子命令
./run.sh check-pins      # 校验 6 个上游仓库是否停在 repo.lock.tsv 的 commit
./run.sh parse           # 论文 artifact -> repro/data/*.csv
./run.sh feasibility     # 44 条目标 bug 的 A/B/C 分级
./run.sh audit           # bug 表与 artifact 原表的一致性审计
```

上游仓库（约 730M）不在版本库里，首次需 `./run.sh setup-repos` 按 lock 文件克隆。
脚本会自动向上几层找 `6app/` 或 `repos/`，也认 `REPO_ROOT` 环境变量，不需要改代码。

## 2026-11-04 交付摘要

### 四个部分

| 部分 | 内容                      | 结论                            |
|------|---------------------------|---------------------------------|
| P0   | 6 仓库按论文 commit 固定  | 6/6 工作区干净，可复现          |
| P1   | 从 commit 历史筛并发缺陷  | 3,105 条；与论文 3,211 只是接近 |
| P2   | Go AST 静态统计 5 类原语  | 73.4% 共享内存，Mutex/chan 居首 |
| P4   | 6 条 bug 的对照复现       | 6/6 buggy 触发、fixed 不触发    |

### P4 复现结果

| bug               | 类型   | buggy 侧                                 | fixed 侧     |
|-------------------|--------|------------------------------------------|--------------|
| `boltdb#341`      | 非阻塞 | `Close()` 立即返回，closeMs=0            | 阻塞 159ms   |
| `boltdb@7fb06fee` | 非阻塞 | 失败率 80~100%（10 次）                  | 失败率 0~10% |
| `grpc#793`        | 阻塞   | TIMEOUT ×3 卡在 server.go:318            | PASS ×3      |
| `grpc#1293`       | 阻塞   | FAIL ×3                                  | PASS ×3      |
| `grpc#1424`       | 阻塞   | FAIL ×3，`doneChan` 永不关闭             | PASS ×3      |
| `grpc#1687`       | 非阻塞 | FAIL ×3，`panic: send on closed channel` | PASS ×3      |

重复次数按 bug 性质区分：`boltdb#341` 是确定性探针，两侧各 1 次；`boltdb@7fb06fee`
属并发竞争，按论文 §4 的做法统计 10 次；四条 grpc 两侧各 3 次。判定依据是
`VERDICT=` 行（boltdb）与 `SUMMARY` 行（grpc）。

截图在 `2026-11-4-1552/results/shots/`：

```text
boltdb341_buggy.png    boltdb341_fixed.png    boltdb7fb06_run4.png
grpc793_repro.png      grpc1293_repro.png
grpc1424_repro.png     grpc1687_repro.png
```

### 未完成 / 待查

- `grpc#1850`：属 end2end 套件，本机连 `TestFailFast` 等基线都卡在 `Dial` 等连接就绪，悬置。
- 其余 35 条 bug 未复现。
- `fix_strategy` / `notes` 两列 171 行全空，阻塞 Table 5–11 的对齐。

## 复现环境

| 项       | 值                                                |
|----------|---------------------------------------------------|
| 系统     | Ubuntu 18.04（VMware 虚机）                       |
| 工具链   | Go 1.10.8，`GOROOT=/usr/local/go1.10.8`           |
| 依赖模式 | `GO111MODULE=off`，`GOPATH=$HOME/gopath`          |
| 依赖时点 | x/net 2018-02、protobuf 2018-03、genproto 2018-03 |

切换 Go 版本必须 `rm -rf $GOPATH/pkg`，否则 `internal/reflectlite` 之类的包会编译失败。

## 复现命令

通用驱动脚本 `repro/scripts/p4_case.sh`，参数依次为
`仓库路径 修复commit 测试名正则 包目录 [次数=3] [超时=30]`。

```bash
# grpc#793（merge commit，脚本自动取 ^1 作 buggy 侧）
bash repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  5a547ed72c "TestServerGracefulStopIdempotent$" test 3 30

# grpc#1687：包目录必须是 transport，不是 test
bash repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  c6b46087ab "TestHandlerTransport_HandleStreams_WriteStatusWrite$" transport 3 60
```

`boltdb#341` 不能用这个脚本：补丁自带的测试无效（`TestDB.Close()` 劫持了
`bolt.DB.Close()` 的调用），必须用 `repro/scripts/08_repro_boltdb.sh` 里的独立探针。

结果五态判定：`PASS` / `FAIL` / `TIMEOUT` / `NOTRUN` / `ERROR`。
`NOTRUN` 专指 `-run` 正则没匹配到任何测试却仍输出 `ok` 的情况，**不能当作通过**。

## 一处已排除的假结果

首次跑 `grpc#1687` 时包目录填成了 `test`，该测试实际位于 `transport` 包，
两侧 6 轮全部 `NOTRUN` —— 但 `go test -run` 在正则空匹配时照样输出 `ok`，
若不识别 `no tests to run` 就会被误当成通过。`p4_case.sh` 已把这种情形单列为
`NOTRUN` 第五种判定，与 `PASS` 严格区分。改对包目录后重跑，两侧各 3 次结果正常。
