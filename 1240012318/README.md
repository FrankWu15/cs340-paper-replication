# 1240012318 · CS340 论文复现

复现对象：*Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）

本目录存放当日交付物，按日期分层，不改动仓库根目录原有的 `README.md` 与 `复现方案.md`。

## 目录

| 目录                  | 内容                                                     |
|-----------------------|----------------------------------------------------------|
| `2026-11-4-1552/`     | 2026-11-04 交付：P0 仓库固定、P1 筛选、P2 静态测量、P4 复现 |

## 2026-11-04 交付摘要

入口文档：`2026-11-4-1552/README.md`（含 26 张表、三大结论与保留意见）。

### 已完成的四个部分

| 部分 | 内容                                     | 结论                                            |
|------|------------------------------------------|-------------------------------------------------|
| P0   | 6 仓库按论文 commit 精确固定             | 6/6 工作区干净，`repo.lock.tsv` 可复现          |
| P1   | 从 commit 历史筛并发缺陷                 | 3,105 条；**与论文 3,211 只是数字接近**，见 §3.1 |
| P2   | Go AST 静态统计 5 类并发原语             | 两大支柱成立：73.4% 共享内存、Mutex/chan 居首   |
| P4   | 6 条 bug 的 buggy/fixed 对照复现         | 6/6 触发且 fixed 侧不触发（详见下）             |

### P4 复现结果

| bug               | 类型   | buggy 侧                            | fixed 侧     | 证据                    |
|-------------------|--------|-------------------------------------|--------------|-------------------------|
| `boltdb#341`      | 非阻塞 | `Close()` 0ms 返回，`Commit` SIGSEGV | 阻塞 159~168ms | 日志 + 截图 ✅          |
| `boltdb@7fb06fee` | 非阻塞 | 失败率 80~100%（10 次）             | 失败率 0~10% | 日志 + 截图 ✅          |
| `grpc#793`        | 阻塞   | 3/3 TIMEOUT（`server.go:318` 死锁） | 3/3 PASS     | 截图 ✅                 |
| `grpc#1293`       | 阻塞   | 3/3 FAIL                            | 3/3 PASS     | 截图 ✅                 |
| `grpc#1424`       | 阻塞   | `doneChan` 永不关闭，调用方空等     | 3/3 PASS     | **缺：无日志无截图** ⚠️ |
| `grpc#1687`       | 非阻塞 | `panic: send on closed channel`     | 3/3 PASS     | **缺：截图参数填错** ⚠️ |

### 未完成 / 待查

- `grpc#1850`：属 end2end 套件，本机连 `TestFailFast` 等基线都卡在 `Dial` 等连接就绪，**不计成功也不计失败**，悬置。
- 其余 35 条 bug 未复现。
- `fix_strategy` / `notes` 两列 171 行全空，阻塞 Table 5–11 的对齐。

## 复现环境

| 项           | 值                                                    |
|--------------|-------------------------------------------------------|
| 系统         | Ubuntu 18.04（VMware 虚机）                           |
| 工具链       | Go 1.10.8，`GOROOT=/usr/local/go1.10.8`               |
| 依赖模式     | `GO111MODULE=off`，`GOPATH=$HOME/gopath`              |
| 依赖时点     | x/net 2018-02、protobuf 2018-03、genproto 2018-03     |

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

## 数据与证据位置

| 类型     | 路径                                              |
|----------|---------------------------------------------------|
| 原始数据 | `2026-11-4-1552/results/data/*.csv`               |
| 运行日志 | `2026-11-4-1552/results/logs/*.log`（仅 boltdb）  |
| 终端截图 | `2026-11-4-1552/results/shots/*.png`（7 张）      |
| 分析报告 | `2026-11-4-1552/report/*.md`（5 篇）              |
| 可复用代码 | `2026-11-4-1552/code/`                          |

## 已知失效截图说明

`results/shots/grpc1687_notrun.png` 记录的是**一次参数错误的运行**：包填了 `test`，
而该测试实际位于 `transport` 包，两侧 6 轮全部 `NOTRUN`。此图保留作为排查记录，
**不作为 `grpc#1687` 的复现证据**。正确参数见上方命令。
