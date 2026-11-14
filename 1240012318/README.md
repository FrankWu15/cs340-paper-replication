# 1240012318 · CS340 论文复现

复现对象：*Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）

本目录存放当日交付物，按日期分层，不改动仓库根目录原有的 `README.md` 与 `复现方案.md`。

## 目录

| 目录              | 内容                                                        |
|-------------------|-------------------------------------------------------------|
| `2026-11-4-1552/` | 2026-11-04 交付：P0 仓库固定、P1 筛选、P2 静态测量、P4 复现 |
| `2026-11-13/`     | 2026-11-13 交付：grpc-go 剩余目标的 P4 复现（3 条成功）     |

## 2026-11-04 交付摘要

入口文档：`2026-11-4-1552/README.md`（含 26 张表、三大结论与保留意见）。

### 已完成的四个部分

| 部分 | 内容                     | 结论                            |
|------|--------------------------|---------------------------------|
| P0   | 6 仓库按论文 commit 固定 | 6/6 工作区干净，可复现          |
| P1   | 从 commit 历史筛并发缺陷 | 3,105 条；与论文 3,211 只是接近 |
| P2   | Go AST 静态统计 5 类原语 | 73.4% 共享内存，Mutex/chan 居首 |
| P4   | 6 条 bug 的对照复现      | 6/6 buggy 触发、fixed 不触发    |

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
`VERDICT=` 行（boltdb）与 `SUMMARY` 行（grpc）。截图含完整命令行、`checkout`
切换记录与逐次结果，位于 `results/shots/`：

```text
boltdb341_buggy.png    boltdb341_fixed.png    boltdb7fb06_run4.png
grpc793_repro.png      grpc1293_repro.png
grpc1424_repro.png     grpc1687_repro.png
```

### 未完成 / 待查

- `grpc#1850`：属 end2end 套件，本机连 `TestFailFast` 等基线都卡在 `Dial` 等连接就绪，**不计成功也不计失败**，悬置。
  → 已在 `2026-11-13/` 解决：原因是次数不够（按概率触发），见下节。
- 其余 35 条 bug 未复现。
- `fix_strategy` / `notes` 两列 171 行全空，阻塞 Table 5–11 的对齐。

## 2026-11-13 交付摘要

入口文档：`2026-11-13/README.md`。这一批只补**复现产物**，P0/P1/P2 的脚本与报告不重复产出，
因此 `2026-11-13/` 下 `code/analysis`、`code/tools`、`data`、`docs`、`report` 只有 `.gitkeep` 占位。

范围是 11-04 那批没做的 grpc-go 目标（`#793/#1293/#1424/#1687` 已在上批完成）。
剩下的 6 条里触发成功 3 条，**目录只保留这 3 条**：

| bug | 类型 | 修复提交 | buggy 侧 | fixed 侧 |
|---|---|---|---|---|
| `grpc#1459` | 阻塞 | `c29d6389` | TIMEOUT ×3，卡在 `NewStream` 与 `keepalive` 同一把 `t.mu` | PASS ×3 |
| `grpc#1667` | 非阻塞 | `a62701e4` | RACE ×3，`ccBalancerWrapper.NewSubConn` 写 `subConns` | PASS ×3 |
| `grpc#1850` | 阻塞 | `484b3ebb` | 50 次循环 DEADLINE 8 次（另轮 10 次），命中率 16%~20% | PASS 50/50 |

`grpc#1850` 更正了 11-04 的悬置结论：不是"连不上"，而是本机从没跑够次数。
它按概率触发（发送配额泄漏，攒够 64KB 才卡死），3 次循环看不出来，要用
`code/cases/grpc-1850/run_loop.sh 50`。命中时的表现是测试内 RPC 卡到 10s deadline
返回 `DeadlineExceeded`（期望 `ResourceExhausted`），而不是 `go test` 整体超时。

`grpc#1662`、`#639`、`#1803` 三条本轮没有构造出触发条件，未纳入交付。

驱动脚本在 `2026-11-13/code/harness/`：`p4_case.sh` 用于补丁自带测试（A 档），
`p4_probe.sh` 为本次新增，用于自写探针（B 档，支持 `-race`）。

## 复现环境

| 项       | 值                                                |
|----------|---------------------------------------------------|
| 系统     | Ubuntu 18.04（VMware 虚机）                       |
| 工具链   | Go 1.10.8，`GOROOT=/usr/local/go1.10.8`           |
| 依赖模式 | `GO111MODULE=off`，`GOPATH=$HOME/gopath`          |
| 依赖时点 | x/net 2018-02、protobuf 2018-03、genproto 2018-03 |

切换 Go 版本必须 `rm -rf $GOPATH/pkg`，否则 `internal/reflectlite` 之类的包会编译失败。

## 复现命令

通用驱动脚本 `2026-11-4-1552/code/repro/scripts/p4_case.sh`，参数依次为
`仓库路径 修复commit 测试名正则 包目录 [次数=3] [超时=30]`。

```bash
# grpc#1293（已在 2026-11-04 验证）
bash code/repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  7df48bee88 "TestInflightStreamClosing$" transport 3 30

# grpc#1687：包目录必须是 transport，不是 test
bash code/repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  c6b46087ab "TestHandlerTransport_HandleStreams_WriteStatusWrite$" transport 3 30

# grpc#793
bash code/repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  5a547ed72c "TestServerGracefulStopIdempotent$" test 3 30
```

结果五态判定：`PASS` / `FAIL` / `TIMEOUT` / `NOTRUN` / `ERROR`。
`NOTRUN` 专指 `-run` 正则没匹配到任何测试却仍输出 `ok` 的情况，**不能当作通过**。

2026-11-13 的三条各自带入口脚本，仓库路径用 `P4_REPO` 覆盖：

```bash
bash code/cases/grpc-1459/run.sh             # 3 次 × 30s
bash code/cases/grpc-1667/run.sh             # 3 次 × 30s，-race
bash code/cases/grpc-1850/run_loop.sh 50     # 按概率触发，必须走 50 次
```

## 数据与证据位置

| 类型       | 路径                                                         |
|------------|--------------------------------------------------------------|
| 原始数据   | `2026-11-4-1552/results/data/*.csv`                          |
| 运行日志   | `2026-11-4-1552/results/logs/`（boltdb 6 份 + `grpc/` 4 条） |
| 终端截图   | `2026-11-4-1552/results/shots/*.png`（7 张）                 |
| 分析报告   | `2026-11-4-1552/report/*.md`（5 篇）                         |
| 可复用代码 | `2026-11-4-1552/code/`                                       |
| 原始数据   | `2026-11-13/results/data/grpc_repro_summary.csv`（3 条）      |
| 运行日志   | `2026-11-13/results/logs/`（三条各 8 份 + `grpc-1850/loop50/`）|
| 可复用代码 | `2026-11-13/code/harness/`（`p4_case.sh`、`p4_probe.sh`）     |

## 一处已排除的假结果

首次跑 `grpc#1687` 时包目录填成了 `test`，该测试实际位于 `transport` 包，
两侧 6 轮全部 `NOTRUN` —— 但 `go test -run` 在正则空匹配时照样输出 `ok`，
若不识别 `no tests to run` 就会被误当成通过。`p4_case.sh` 已把这种情形单列为
`NOTRUN` 第五种判定，与 `PASS` 严格区分。改对包目录后重跑，两侧各 3 次结果正常。
