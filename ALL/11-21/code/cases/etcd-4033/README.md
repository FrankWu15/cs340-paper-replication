# etcd#4033 — raftexample 提案通道死锁

| 项 | 值 |
|---|---|
| 论文条目 | `etcd#4033`（blocking，`cause_group=message_passing`） |
| 修复提交 | `b7cf2385e6874d07f32f183007e50f4448b7e3a2`（2015-12-19） |
| buggy 基线 | `bff857dc2`（`b7cf2385^`，2015-12-17） |
| 代码位置 | `contrib/raftexample/raft.go` → `serveChannels()` |
| 触发 | `TestProposeOnCommit`（补丁自带，107 行，buggy 版本无此文件，从 fix 移植） |
| 环境 | Ubuntu 18.04 / Linux 4.15.0-213 / go1.10.8 / `GOPATH=Godeps/_workspace:$GOPATH` |
| 结论 | **REPRODUCED** — buggy 挂死，fixed 通过 |

## 机理

`serveChannels()` 在同一个 `select` 里既接收客户端提案又消费 `node.Ready()`：

```go
case prop, ok := <-rc.proposeC:
        rc.node.Propose(context.TODO(), []byte(prop))   // 同步阻塞
case rd := <-rc.node.Ready():
        ...
        rc.publishEntries(rd.Entries)                  // 向 commitC 发送
        rc.node.Advance()
```

`node.Propose()` 内部要把提案写进 raft 的 `propc`，而 `propc` 只有在 `Ready()` 被消费并 `Advance()` 之后才会腾空。提案量大时，`Propose()` 阻塞在同一个 goroutine 里，`Ready()` 再也得不到处理，形成自锁。

修复方式是把「发送提案」挪到独立 goroutine（`stopc` 负责关闭通知），事件循环只处理 raft 状态机更新。

## 实测

```
[buggy] HEAD=bff857dc2  test=107 lines
[buggy] exit=1  symptom=HANG(test timed out)      # 45s 无进展
[fixed] HEAD=b7cf2385e  test=107 lines
[fixed] exit=0  symptom=PASS                       # 1.414s
```

buggy 侧 45s 超时后 runtime 打出全部 goroutine 栈，**三个 raftexample 节点的 `serveChannels` 同时卡住**：

| goroutine | 位置 | 说明 |
|---|---|---|
| 节点 1 | `raft.go:207` (`publishEntries`) | 发布已提交条目时阻塞 |
| 节点 2 | `raft.go:207` (`publishEntries`) | 同上 |
| 节点 3 | `raft.go:189` (`select`) | 事件循环空转，等不到推进 |

判定依据不是 `-race`（该测试自身在 `raftexample_test.go:86/101` 有变量竞争，两个版本都会报，不能用作判据），而是**全进程 45s 无进展 + 栈落在 `serveChannels`**。

## 文件

```
etcd-4033/
├── README.md
├── run.sh                       # 双侧复现（含从 fix 移植测试）
├── logs/etcd4033_buggy.log      # 1988 行，含完整 goroutine dump
└── logs/etcd4033_fixed.log      # 160 行，PASS
```

## 复现

```bash
# 虚拟机 192.168.47.128，仓库 /home/li/gopath/src/github.com/coreos/etcd
bash run.sh
```

`run.sh` 会先 `git checkout bff857dc2`，用 `git show b7cf2385:contrib/raftexample/raftexample_test.go` 把测试文件补进 buggy 树，跑 45s 超时；再切到 `b7cf2385` 跑 fixed 侧。

## 对论文的意义

- 计入 41 条复现分母（blocking），使 etcd 从 3/13 → 4/13、总计 14/41 → 15/41。
- 这条是**裸进程、单机 3 节点**，没有真实 server 那种常驻 IO 协程；若再跑内置死锁检测器（`checkdead()`），有较大概率像 `boltdb#392` 一样报出 `all goroutines are asleep`，可作为 Table 8 `real-repo` 行的第二个检出点（当前 1/6）。
