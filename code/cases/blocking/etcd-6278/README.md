# etcd#6278 — Election 前缀与既有 key 重叠，竞选死等

| 项 | 值 |
|---|---|
| 论文条目 | `etcd#6278`（blocking，`cause_group=message_passing`） |
| 修复提交 | `9497e9678cdc64785847993c96ff2748e09ef9a1`（2016-08-28） |
| buggy 基线 | `48f4a7d03`（`9497e967^`） |
| 代码位置 | `clientv3/concurrency/election.go` → `NewElection()` / `Campaign()` |
| 触发 | 先 Put `testa`，再 `NewElection(s, "test")` 并 `Campaign`（= fix 自带测试的核心三行） |
| 环境 | Ubuntu 18.04 / Linux 4.15 / go1.10.8 / etcd 3.0.0+git 单机 server |
| 结论 | **REPRODUCED** — buggy 等满 5s 超时，fixed 立即当选 |

## 机理

`NewElection(s, pfx)` 存下来的 `keyPrefix` 直接用于两件事：拼自己的候选 key，以及 `waitDeletes()` 里做前缀 range 查询。当选前缀 `test` 与既有 key `testa` 重叠时：

- 既有 key `testa` 落在 `test` 的 range 里 → buggy 认为「前面还有人排队」；
- 但它实际等的 key 是 `test/<lease>`，那个 key 永远不存在 → **永远等不到**，`Campaign` 挂到 context 截止。

修复把 `keyPrefix` 改成 `pfx + "/"`，把自己和别人的 key 都放到带斜杠的命名空间里，`testa` 不再被算进 `test/` 的 range。

## 实测

```
[buggy] HEAD=48f4a7d03
CAMPAIGN_FAIL after 5.00s: context deadline exceeded
[fixed] HEAD=9497e9678
CAMPAIGN_OK after 0.00s
```

服务端是两侧共用的同一个单机 etcd（`etcdserver 3.0.0+git`），差异只来自客户端库版本 —— 这正是该 bug 的属性（纯客户端逻辑）。`logs/etcd6278_server.log` 显示 server 全程正常，只在最后收到 TERM 退出，排除了服务端干扰。

## 为什么不用 integration 测试

fix 自带的 `TestElectionOnPrefixOfExistingKey` 在 `integration` 包里。本环境跑该包时，**buggy 与 fixed 两侧都在 `member.Launch` 阶段卡住 300s**（`logs/../results/logs/etcd6278_integration_*.log`），说明是测试集群框架与 Ubuntu 18.04 + go1.10.8 不兼容，不是 bug 判据。改用「真实 server 二进制 + 20 行驱动器」后 8 秒出结果。

驱动器 `probe/main.go` 与 fix 自带测试的触发条件逐行对应（Put `testa` → NewSession → NewElection(`test`) → Campaign），只是省掉了测试框架。

## 文件

```
etcd-6278/
├── README.md
├── run.sh                    # 起 server、编译两侧 client、各跑一次
├── probe/main.go             # 触发器（等价于 fix 自带测试的核心路径）
├── results/verdict.txt
└── logs/
    ├── etcd6278_buggy.log    # CAMPAIGN_FAIL 5.00s
    ├── etcd6278_fixed.log    # CAMPAIGN_OK 0.00s
    └── etcd6278_server.log   # 服务端全程正常
```

## 对论文的意义

- 计入 41 条分母（blocking），etcd 5/13 → 6/13。
- 与 #4033/#4474 不同，这条**不能**用内置死锁检测器判（进程没有卡死，只是客户端在等 context），论文里它归 blocking 但症状是「调用永不返回」，属于 detector 抓不到的那一类 —— 可作为 Table 8 分母里「检测器失效」的又一个样本。
