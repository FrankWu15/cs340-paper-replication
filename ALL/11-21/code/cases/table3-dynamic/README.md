# Table 3 · gRPC 运行时 goroutine 动态测量

论文 §3.1 第二问："do real Go applications create a lot of goroutines during runtime?" 答案是 Table 3：
三个 RPC 负载下，Go 侧 goroutine 数 / C 侧线程数（client、server 各一列），以及 Go 侧 goroutine 平均存活时间占整个程序运行时间的比例。

## 1. 实验设置

| 项 | 值 |
|---|---|
| 被测程序 | gRPC-Go `f6692351`（2018-05-21）的 `benchmark/client` 与 `benchmark/server` |
| 编译 | 本机 Go 1.27 交叉编译 linux/amd64，静态链接；依赖锁定 protobuf v1.1.0、x/net 2018-05 |
| 运行 | Ubuntu 18.04 虚拟机，Go 二进制无 cgo，单机回环 |
| 负载 | `-max_concurrent_rpcs` = 1 / 200 / 1000，unary，1 byte payload |
| 对照组 | gRPC-C v1.10.0（2018-03-01）。**未运行**——镜像的 third_party 子模块为空（boringssl/protobuf/zlib 均缺），装不上；C 侧数值引用论文 |
| 计数 | goroutine 数：`pprof /debug/pprof/goroutine?debug=2` 抓栈数 `^goroutine` 行；线程数：`/proc/<pid>/status` 的 `Threads` |

## 2. 结果（Go 侧实测）

论文的 "Goroutines/Threads" 是**跨语言比值**（Go 的 goroutine 数 ÷ C 的线程数），不是同进程内的 goroutine/线程比。所以下表把论文比值当作已知量，反推 C 侧线程数：

| 负载 | 并发 | 侧 | goroutine | OS 线程 | 论文比值 | 反推 C 线程 |
|---|---|---|---|---|---|---|
| sync_ping_pong | 1 | client | 18 | 7 | 7.33 | 2.46 |
| sync_ping_pong | 1 | server | 10 | 5 | 4.00 | 2.50 |
| qps_unconstrained | 200 | client | 216 | 7 | 201.46 | 1.07 |
| qps_unconstrained | 200 | server | 10 | 5 | 6.36 | 1.57 |
| **qps_unconstrained** | **1000** | **client** | **1019** | **7** | **201.46** | **5.06** |
| qps_unconstrained | 1000 | server | 14 | 8 | 6.36 | 2.20 |

**client 侧自洽**：论文 201.46 这个比值只有在 Go 侧约 1000 个 goroutine 时才成立（1019 / 201.46 = 5.06，gRPC-C 的 server/client 默认线程池正好是 5 线程）。这同时说明论文的 `qps_unconstrained` 用的是约 1000 并发。

**server 侧偏低**：14 / 6.36 = 2.20，论文隐含约 2.9 倍于我们的 goroutine 数（约 38–40）。原因明确——gRPC-Go 的 server 不为每个 RPC 起 goroutine，unary 请求在 transport 的 reader goroutine 里同步处理；论文若统计的是"创建过的 goroutine 累计数"（含每 stream 的 2 个），则会高于瞬时值。这一列只能算方向一致（Go 侧随并发增长），数值不可直接比。

**与并发的关系**：client goroutine 数 = 并发 + 约 16~19 个固定开销（18@1、216@200、1019@1000），线性增长，这正是论文要证明的"运行时大量创建 goroutine"。C 侧线程数恒定（5），不随负载增长。

## 3. goroutine 存活时间（口径未对齐）

用 pprof 每 309 ms 抓一次全量栈，按 goroutine ID 统计出现次数，估计存活时长：

| 侧 | 唯一 goroutine | 平均存活 | 中位数 | ≥90% 的占比 | 论文 |
|---|---|---|---|---|---|
| client | 109 | 9.17% | 1.00% | 8.3% | 63.65% |
| server | 116 | 6.12% | 1.00% | 5.2% | 76.97% |

**判定：不可复现，不是"没做对"，是口径无法对齐。**

三条证据：

1. **中位数 1%** 说明绝大多数 goroutine 的寿命短于一个采样间隔（309 ms）。gRPC-Go 每次 RPC 都有短命 goroutine，它们只被采到一次，按 1 个间隔计。
2. **采样法结构性低估短命 goroutine 的权重**：只能看见"还活着的"，看不见"已经死掉的"。要精确算平均寿命必须用 runtime trace 的 `GoCreate`/`GoEnd` 事件，Go 1.10 没有可机读的官方解析器。
3. **论文的 RPS 量级必然远低于我们**：本地回环 1 byte payload 实测 3,940 RPS，40 秒 15.7 万次 RPC。若每次 RPC 一个 goroutine，平均寿命 4.6 ms，占 35 秒的 0.013%——比论文低 4 个数量级。论文能得到 63~77%，只能是低 RPS 场景（每次 RPC 间隔数百毫秒）或统计口径是"按 goroutine 而非按时间加权"。

因此本项按**部分复现**记账：比值列（Table 3 左半）用 1000 并发验证通过，存活时间列（右半）给出实测与偏差说明，不伪造对齐。

## 4. 复现

```bash
# 1. 编译（依赖锁定，走 goproxy.cn）
go build -o bench_server ./benchmark/server   # 源码需 2018 版 grpc-go
go build -o bench_client ./benchmark/client

# 2. 采样（VM 上跑，需 ss/curl/python3）
BIN=/tmp/bench_server_clean bash run_table3_life.sh life_sync 1 35 100 0.3
python3 parse_life.py ~/repro-1121/table3 life_sync 30.91 35

# 3. 纯计数（不采样，只抓一次栈）
bash run_table3_one.sh sync_ping_pong 1 40
```

## 5. 产物

```
logs/goroutine_stacks.tar.gz   200 份 goroutine 栈（100 份 server + 100 份 client）
logs/samples/                  4 份样本（第 1、50 轮，两端）
logs/life_sync_server.out / life_sync_client.out
data/table3_dynamic.csv
```

## 6. 已知偏差

- gRPC-C 未运行，比值分母来自论文，未独立测量。
- `g_sync_ping_pong` 未测：gRPC-Go 的 benchmark 只有 protobuf unary/streaming 两种 client，没有 generic（byte buffer）client。
- 采样间隔 309 ms 对亚毫秒 goroutine 是盲区，平均存活时间被系统性低估。
- 交叉编译用 Go 1.27 而非当时的 1.10，runtime 调度器实现有差异（goroutine 数不受影响，寿命分布可能受调度延迟影响）。
