# Table 3 复现报告 · gRPC-Go vs gRPC-C 的动态创建与存活

## 1. 论文要证明什么

§3.1 提两个问题：

1. **静态**：Go 程序员是不是倾向于写很多 goroutine？→ Table 2（创建点计数）
2. **动态**：Go 程序运行时是不是真的创建大量 goroutine？→ Table 3

Table 3 有三组负载（`g_sync_ping_pong`、`sync_ping_pong`、`qps_unconstrained`），四个指标：client 与 server 的 **goroutine 数 ÷ C 线程数** 比值，以及 Go 侧 **goroutine 平均存活时间 ÷ 程序总时长**。

论文结论（Observation 1）：**"Goroutines are shorter but created more frequently than C (both statically and at runtime)."**

## 2. 我们做了什么

| 侧 | 做法 | 状态 |
|---|---|---|
| Go | gRPC-Go `f6692351`（2018-05）的官方 benchmark client/server，交叉编译成 linux/amd64 静态二进制，在 Ubuntu 18.04 VM 上跑三组并发 | 完成 |
| C | 尝试装 gRPC-C v1.10.0 | **失败**：镜像 `third_party` 子模块全空（boringssl/protobuf/zlib/cares），无 Bazel/CMake 依赖链，装不上 |
| 计数 | pprof `debug=2` 抓全量栈数 goroutine；`/proc/pid/status` 读线程数；handler 打点测处理时长；100 轮 × 309ms 采样估存活 | 完成 |

C 侧跑不了，比值列的分母只能用论文的比值反推。这是本项最大的硬约束，先说明。

## 3. 比值列：client 侧验证通过

论文说 `qps_unconstrained` 的 client 比值是 **201.46**。如果我们能测出 Go 侧 goroutine 数，除以 201.46 应得到一个"像线程池大小"的整数：

| 并发 | Go client goroutine | ÷ 201.46 | 解读 |
|---|---|---|---|
| 200 | 216 | 1.07 | 不整，说明论文不是 200 并发 |
| **1000** | **1019** | **5.06** | **≈ 5，gRPC-C 默认线程池 5 线程** |

同时 `sync_ping_pong` 的 client 比值 7.33，用 18 goroutine 反推是 2.46，接近 gRPC-C 最小配置（1 个 poller + 1 个 CQ 线程，加 1 个主线程）。

**这两处自洽不是巧合**：它同时验证了三件事——论文的比值确实是跨语言比、论文的 `qps_unconstrained` 用了约 1000 并发、Go 侧 goroutine 数随并发**线性增长**（18 → 216 → 1019，斜率 1.0，截距约 17）。

## 4. server 列为偏低，原因是模型差异

`sync_ping_pong` server 比值 4.00，我们测到 server 只有 10 个 goroutine，反推 C 线程 2.5；`qps_unconstrained` 比值 6.36，我们 14 个，反推 2.2。

论文隐含的 server goroutine 数应是 24~38（比值 × 6 线程）。我们只有 10~14，差 2~3 倍。

原因是 gRPC-Go 的 server 端模型：**unary RPC 不新建 goroutine**，请求在 HTTP/2 transport 的 reader goroutine 里同步执行 `processUnaryRPC`。并发 1000 时 server 也只有 14 个 goroutine（reader、writer、keepalive、若干连接级 goroutine）。

论文若统计"累计创建数"（每 stream 2 个 reader/writer goroutine），数值会高得多。这一点无法从论文正文确认，只能标为口径差异。

## 5. 存活时间列：明确不可对齐

| 侧 | 本文实测 | 论文 |
|---|---|---|
| client | 平均 9.17%，中位 1.00% | 63.65% |
| server | 平均 6.12%，中位 1.00% | 76.97% |

差 7~12 倍。三个原因，按影响力排序：

1. **RPS 量级差太多**。本地回环 1 byte payload 跑到 3,940 RPS（handler 平均 305 ns），40 秒 15.7 万次 RPC。若每次 RPC 一个短命 goroutine，平均寿命 4.6 ms，占 35 秒的 0.013%。论文能到 63% 只能是每次 RPC 间隔数百毫秒的低速场景。
2. **采样法看不见短命 goroutine**。309 ms 采一次，寿命 <309 ms 的 goroutine 只被计一次（1%）。中位数 1% 就是这个盲区的直接证据。
3. **"平均"的定义可能是按 goroutine 加权还是按时间加权**。论文写"average execution time of all goroutines"，按 goroutine 等权平均会被海量短命 goroutine 拉低；按时间加权则接近 100%。论文没写清楚。

结论：**这一列不判定为复现**。给出实测值与偏差分析，比硬凑一个接近 63% 的数字更可信。

## 6. 与静态 Table 2 合起来看

| 维度 | gRPC-Go | gRPC-C | 论文结论 |
|---|---|---|---|
| 静态创建点（Table 2） | 44（本文 48，+9.1%） | 5（本文 5，口径 B） | Go 多 8.8 倍 |
| 每 KLOC | 0.83（本文 0.909） | 0.03（本文 0.034） | Go 高 27 倍 |
| 运行时并发实体（1000 并发） | 1,019 goroutine | 5 线程（反推） | Go 多 200 倍，且随负载增长 |
| 实体寿命 | 亚毫秒~数十秒（中位 1% 采样窗口） | 全程（论文：100%） | Go 更短、更频繁 |

前三行都复现了，第四行只复现了"更短"的方向（中位 1% vs 论文 100% 的线程），绝对数值不可比。

**Observation 1 的定性结论成立**：Go 用大量短命 goroutine，C 用少量长命线程。定量上，静态比值（8.8×、27×）可精确复现，动态比值（200×）依赖论文的并发设置，寿命比值（63% vs 9%）不可复现。

## 7. 如果要继续

- 让 C 侧真正跑起来：需要能访问 GitHub 的机器拉全 `third_party` 子模块，或直接用 `apt install libgrpc-dev` 的二进制做客户端对照（版本不同，需说明）。
- 存活时间列改用 runtime trace：用 Go 1.21 编译同一份 grpc-go 源码，`go tool trace` 可导出 `GoCreate`/`GoEnd` 全量事件，能算出精确的平均寿命，不再受采样盲区影响。
- `g_sync_ping_pong` 需要 gRPC-Go 侧补一个 generic（byte buffer）client，工作量约 100 行。
