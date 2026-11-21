# 11-18 批次说明：etcd 三条 blocking 复现

本批只做一件事：从 `data/repro_targets.csv` 的 **13 条 etcd 目标**里挑 3 条动手复现，产物按 11-14 的统一结构落在本目录。不含报告、不含统计，也不覆盖 11-14 的既有结果。

## 1 为什么是这三条

13 条 etcd 目标里，blocking 8 条、non-blocking 5 条。挑选标准按优先级：

1. **机理能在单机、单进程内闭合** —— 不需要 etcd 集群、Raft 多节点、外部网络对端；
2. **修复能落到一处具体代码** —— 补丁里能指出"哪一行把锁/通道放错了"，便于最小复现保真；
3. **判定信号确定** —— 必须能被 Go 内置死锁检测器以 `all goroutines are asleep - deadlock!` 抓到，不依赖超时或概率。

据此选出的三条，覆盖三种不同的阻塞形态：

| 条目 | 形态 | 一句话机理 |
|---|---|---|
| `etcd#6937` | 同一 goroutine 的锁重入 | `bcast()` 持写锁又调 `size()`，`size()` 取同一把 RWMutex 的读锁 |
| `etcd#5509` | 两 goroutine 的锁顺序反转（ABBA） | `acquire()` 是 `client→r`，`reconnect()` 是 `r→client`，且后者取写锁 |
| `etcd#4679` | 持锁等待被等待方 | `Close()` 全程持 `c.mu` 等 watcher 退出，watcher 退出又要 `c.mu` |

三条都在论文的 41 条集合内（`Reproduced?=1`），因此可以直接进 **Table 8 的分子/分母**，不属于"集合外补充复现"。

## 2 被否掉的候选及原因

| 条目 | 否掉的原因 |
|---|---|
| `etcd#4474` | 走 `contrib/raftexample` 的重启路径，要单节点 Raft + WAL 重放，必须起集群 |
| `etcd#4033` | 也是 raftexample，死锁依赖 raft 节点内部"写 Ready 阻塞"，用一个假 node 模拟就成了自证，保真度撑不住 |
| `etcd#6278` / `#5199` / `#5349` | 都是 election/lock 的 key 与 lease 语义导致的死锁，必须跑真实 etcd KV + 会话过期，单机最小化会失真 |
| `etcd#3060` / `#3593` / `#4876` / `#7816` / `#8183` | 全部是 non-blocking（数据竞态/原子性），需要 `-race`。本机 `-race` 运行时缺 DLL（`0xc0000139`），要先在虚拟机上确认 `go1.10.8 -race` 可用再做 |

后三条 non-blocking 里，`etcd#8183`（compactor 的 `fakeRevGetter.rev` 无同步）和 `etcd#7816`（`ctx.String()` 读可变值）结构最小，是下一批的首选。

## 3 方法与保真

沿用 11-14 `etcd-6873` 的做法：**最小可编译复现 + 真实源码取证**。

- 每个 case 的 `results/real-source.txt` 是从本地 etcd 克隆（`output/6app/etcd`）里用 `git show <fix>^:<path>` 导出的**原生文件**，不是转述；
- `buggy/main.go` 保留真实代码的方法名、加锁位置、调用顺序，只把 `clientv3`/`grpc`/metrics 依赖换成本地替身；
- `fixed/main.go` 只改补丁里那几行，其余与 buggy 逐行一致，保证"唯一变量是修复本身"。

这与"自己写一个会死锁的小程序"有本质区别：判据是 `README` 第 2 节能指到上游具体行号，第 7 节能说清哪些依赖被替换、为什么替换不影响锁语义。

## 4 环境

| 项 | 值 |
|---|---|
| 主机 | `li@192.168.47.128`（与 11-13 同一台） |
| 系统 | Ubuntu 18.04，Linux 4.15.0-213-generic，x86_64 |
| Go | `/usr/local/go1.10.8`（2018 年工具链，死锁检测语义与论文一致） |
| 运行方式 | 三个 case 打包上传到 `~/repro-1118`，逐个 `./run.sh`，日志回传 |

日志里的路径是虚拟机上的 `/home/li/repro-1118/...`，没有本机绝对路径。

## 5 结果

| 条目 | buggy | fixed | 判定 |
|---|---|---|---|
| `etcd#6937` | DEADLOCK（exit=2） | CLEAN（exit=0） | 成立 |
| `etcd#5509` | DEADLOCK（exit=2） | CLEAN（500 轮全过） | 成立 |
| `etcd#4679` | DEADLOCK（exit=2） | CLEAN（exit=0） | 成立 |

汇总见 `results/data/repro_summary_1118.csv`，逐条证据在各 case 的 `logs/`。

## 6 剩余 10 条的建议顺序

1. `etcd#8183`、`etcd#7816` —— non-blocking，结构最小，先把 `-race` 链路在虚拟机上打通；
2. `etcd#3060`、`#4876`、`#3593` —— 其余 non-blocking，仍可用最小复现；
3. `etcd#4474`、`#4033` —— 需要 raftexample，建议合并成一个 case（同一份 raft 依赖）；
4. `etcd#6278`、`#5199`、`#5349` —— election/lock 语义类，成本最高，放最后或写进限制。

## 7 与 11-14 的关系

- 本目录**不复制** `code/harness/`：`p4_case.sh`、`p4_probe.sh` 等在 11-14 里只有一份，本批的 `run.sh` 是各 case 自带的入口；
- 本批的 3 条如果并回 11-14，落点是 `code/cases/blocking/etcd-{6937,5509,4679}/`，并在 `results/data/repro_summary.csv` 追加 3 行、把 blocking 从 13 条更新为 16 条；
- 合并前需决定：是保留"按日期分批"（11-13、11-14、11-18 并列），还是只留一份最新的合集。
