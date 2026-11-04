# gRPC-Go 并发缺陷复现

复现 *Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）数据集中
gRPC-Go 的 1 个并发缺陷，做 **buggy 提交 vs 修复提交** 的对照实验。

数据来源：[`system-pclub/go-concurrency-bugs`](https://github.com/system-pclub/go-concurrency-bugs)

## 结果一览

| 编号 | 缺陷 | 类型 | 修复提交 | 缺陷版 | 结果 |
|---|---|---|---|---|---|
| 01 | `DialContext` 中 goroutine 泄漏导致永久阻塞 | blocking | `4e56696c6c5a` | `39c8c386` | 缺陷版 FAIL / 修复版 PASS |

详细分析见 [case.md](cases/01-lbwatcher-leak/case.md) 与 [../../report/REPORT.md](../../report/REPORT.md)，
原始输出见 [../../results/grpc-go/](../../results/grpc-go/)。

## 复现方法

与 BoltDB 部分采用同一套前后对照逻辑，但构建方式不同：

1. 取修复提交的父提交作为缺陷版源码，修复提交本身作为修复版源码；
2. 将两版本分别置于独立工作目录，依赖版本固定到修复提交所处时间点（2017-08）；
3. 以修复提交新增的回归测试 `TestClientLBWatcherWithClosedBalancer` 作为触发用例，
   在两版本上分别运行；
4. 缺陷版 FAIL、修复版 PASS，即为对照成立。

## 快速开始

环境要求：Go 1.22.9，module 模式。

```bash
export GO111MODULE=on
export GOPROXY=https://goproxy.cn,direct
export GOSUMDB=off
export GOFLAGS=-mod=mod

# 分别在缺陷版与修复版工作目录放置对应源码快照，
# 并复制 notes/01-lbwatcher-leak.go.mod 为 go.mod（go.sum 同理），然后：
go test -run TestClientLBWatcherWithClosedBalancer -v
```

缺陷版预期输出 `FAIL: ... didn't close doneChan after 100ms`，修复版预期 `PASS`。

构建环境、依赖版本固定方法与已知网络问题见 [notes/env.md](notes/env.md)；
两版本源码差异（仅 2 个文件）见 [notes/source-diff.txt](notes/source-diff.txt)。

## 目录

```
.
├── README.md                        本文件
├── cases/
│   └── 01-lbwatcher-leak/
│       └── case.md                  完整记录：机理、触发条件、结果、可靠性说明
├── patches/
│   └── 01-lbwatcher-leak.patch      修复提交原文（含 commit message 与 diff）
└── notes/
    ├── env.md                       构建环境、依赖版本固定记录
    ├── source-diff.txt              两版本源码差异（仅 2 个文件）
    ├── 01-lbwatcher-leak.go.mod     实际使用的 go.mod
    └── 01-lbwatcher-leak.go.sum     实际使用的 go.sum
```

## 许可

本目录的复现文档为课程作业用途。`patches/` 中的 diff 来自
[grpc/grpc-go](https://github.com/grpc/grpc-go) 上游提交（Apache-2.0），
版权归原作者所有。
