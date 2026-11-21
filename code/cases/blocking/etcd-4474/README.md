# etcd#4474 — raftexample 单节点重启崩溃

| 项 | 值 |
|---|---|
| 论文条目 | `etcd#4474`（blocking，`cause_group=message_passing`） |
| 修复提交 | `0cb304ec61019c5ff2f6260245ef30fb6dc9711a`（2016-02-09） |
| buggy 基线 | `5e47ba3fa`（`0cb304ec^`） |
| 代码位置 | `contrib/raftexample/raft.go` → `replayWAL()` / `publishEntries()` |
| 触发 | 单节点跑一次 → 写入 → 终止 → **用同一 waldir 再启动** |
| 环境 | Ubuntu 18.04 / Linux 4.15.0-213 / go1.10.8 / `GOPATH=Godeps/_workspace:$GOPATH` |
| 结论 | **REPRODUCED** — buggy 重启即 SIGSEGV，fixed 重启后正常选主并提交 |

## 机理

`raftNode.waldir` 是相对路径 `raftexample-<id>`，所以同一目录下重启会 replay 同一个 WAL。

buggy 的 `replayWAL()` 直接调用 `publishEntries()`，而后者对 `raftpb.EntryConfChange` 会执行：

```go
rc.node.ApplyConfChange(cc)   // rc.node 尚未创建 —— replay 阶段只 replay，不建 node
```

单节点第一次运行必然写入一条 `ConfChangeAddNode`（自己加入集群），于是**重启 replay 到这条时 `rc.node == nil`，nil 解引用崩溃**。修复把 replay 改成走正常 raft loop（`lastIndex` 之后才发 nil commit 信号），并去掉 `rc.node` 的空指针路径。

## 实测

```
buggy: put1=204 get1=[v1] | put2=000 get2=[]      alive_after=no
fixed: put1=204 get1=[v1] | put2=204 get2=[v2]    alive_after=yes
```

- **buggy**：第二次启动进程直接死掉，`put2` 连接失败（`000`）。`run2.log`：

```
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x20 pc=0x72b05f]

main.(*raftNode).publishEntries(0xc4200a10e0, 0xc420021560, 0x3, 0x4, 0x0)
        .../contrib/raftexample/raft.go:107
main.(*raftNode).replayWAL(...)
        .../contrib/raftexample/raft.go:157
main.(*raftNode).startRaft(...)
        .../contrib/raftexample/raft.go:173
```

- **fixed**：`1 became leader at term 3` → `put2=204` → `get2=[v2]`，重启后可写可读。

## 判据说明

HTTP 的 `PUT` 是**乐观返回**（写入 `proposeC` 就回 204，不等 commit），所以不能只看 `put2`。真正的判据是 **`get2` 是否读得到刚写的值** —— 这要求提案被 raft 提交并 apply。buggy 侧进程已崩，`get2` 为空。

本条的复现形态是 **CRASH（重启路径不可用）**，不是 HANG。修复提交的说明同时提到两种症状（"crashes WAL replay" 与 "deadlock because it had the wrong raft HardState"），本环境命中前者。

## 文件

```
etcd-4474/
├── README.md
├── run.sh                          # 构建两侧 + 各跑「启动→写→重启→再写」
├── results/verdict.txt
└── logs/
    ├── etcd4474_buggy_run1.log     # 首启正常
    ├── etcd4474_buggy_run2.log     # 重启 SIGSEGV
    ├── etcd4474_fixed_run1.log
    └── etcd4474_fixed_run2.log     # 重启选主成功
```

## 对论文的意义

- 计入 41 条分母（blocking），etcd 4/13 → 5/13。
- 与 `etcd#4033` 同属 raftexample，**同一套构建/环境**，两条合计只需一次 `go build`。
