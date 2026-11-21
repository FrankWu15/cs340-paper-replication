# cases —— 复现的 bug，按 blocking / non-blocking 分两类

一条 bug 一个目录，目录名统一为 `<仓库>-<编号>`。每个目录**自包含**：说明、可运行代码、
原始日志、截图都在里面，不依赖别的目录。

分类沿用论文的划分：

- **blocking**（论文 §5）——进程卡住、不推进；可观测信号是死锁/超时。
- **non-blocking**（论文 §6）——进程总能跑完；问题只在数据竞争或中途崩溃上，
  不加 `-race` 或不看崩溃位置就看不见。

## blocking（15 个目录 / 17 条 bug）

| 目录 | bug | 症状 | 判定（buggy → fixed） | 负责 |
|---|---|---|---|---|
| `boltdb-392/` | boltdb#392 | channel 在临界区内等待 + RWMutex 循环等待 | 死锁 10/10 → 干净退出 | 吴德诚 |
| `boltdb-begin-lock-leak/` | boltdb `defdb743c` | `beginTx` 错误分支漏解锁 | 死锁 → 返回 `ErrDatabaseNotOpen` | 许汝轩 |
| `cockroachdb-1cc69980/` | cockroachdb `1cc69980` | gossip 关闭路径 `break` 前漏 `Unlock` | 死锁 → 干净退出 | 吴德诚 |
| `etcd-6873-double-lock/` | etcd#6873 + etcd 双重加锁 | 临界区内 `<-donec`；`Sync()` 自我重入读锁 | 两条均死锁 → 干净退出 | 吴德诚 |
| `grpc-793/` | grpc#793 | 二次 `GracefulStop` 自我死锁 | TIMEOUT ×3 → PASS ×3 | 李振炜 |
| `grpc-1293/` | grpc#1293 | 删除在途流不通知，调用方等不到 `StreamError` | FAIL ×3 → PASS ×3 | 李振炜 |
| `grpc-1424/` | grpc#1424 | `lbWatcher` 泄漏，`doneChan` 永不关闭 | FAIL ×3 → PASS ×3 | 李振炜、许汝轩 |
| `grpc-1459/` | grpc#1459 | keepalive 唤醒令牌不复位，持 `t.mu` 阻塞 | TIMEOUT ×3 → PASS ×3 | 李振炜 |
| `grpc-1850/` | grpc#1850 | 发送配额泄漏，写大消息卡到 deadline | DEADLINE 8/50 → PASS 50/50 | 李振炜 |
| `kubernetes-62464-20697/` | k8s#62464 + k8s#20697 | 双重 `RLock()`；`defer RUnlock` 注册过晚 | 两条均死锁 → 干净退出 | 吴德诚 |
| `moby-17176/` | moby#17176 | `cleanupDeletedDevices()` 提前 return 漏 `Unlock` | 最小程序超时 → 拿到锁 | 朱奕铭 |
| `moby-8909/`† | moby#8909 | 持锁调用 `GetExitCode()`，同一把不可重入锁再 Lock 一次 | 3/3 超时 → 3/3 返回 | 李振炜 |
| `moby-256/`† | moby#256 | 先读完 stdout 再读 stderr，子进程写满 stderr 缓冲后互等 | 3/3 超时 → 3/3 完成 | 李振炜 |
| `moby-27782/`† | moby#27782 | 关闭后仍向已无消费者的 `Msg` 送最后一条 | 3/3 超时 → 3/3 返回 | 李振炜 |
| `kubernetes-30872/`† | k8s#30872 | 持锁调用 `HasSynced()`，其回调再拿同一把锁 | 3/3 超时 → 3/3 返回 | 李振炜 |

† 为 2026-11-21 补充复现。形态不统一，别当成一回事：`moby-8909` 与 `moby-256` 是
**real-repo**（直接执行上游函数本体），`moby-27782`、`kubernetes-30872` 是 **minimal**。
`moby-27782` 的 real-repo 试过但结论不成立，不计入 real-repo 那一栏。依据与命令见
[`real-repo-notes.md`](real-repo-notes.md)。

`etcd-6873-double-lock/` 与 `kubernetes-62464-20697/` 各覆盖**两条** bug：它们在原提交里
共用一个 Go module 与一套脚本（`internal/bugs/` 下两个文件、`cmd/repro` 一个入口），
拆开会把 build 与结果目录一起拆坏，所以按工程保留，目录名把两条 bug 都写全。

## non-blocking（10 个目录 / 10 条 bug）

| 目录 | bug | 症状 | 判定（buggy → fixed） | 负责 |
|---|---|---|---|---|
| `boltdb-341/` | boltdb#341 | `Close()` 不等未完成的写事务 | `Commit` SIGSEGV/panic → `Close` 阻塞后正常提交 | 李振炜、许汝轩 |
| `boltdb-7fb06fee/` | boltdb `7fb06fee` | 读事务共享 meta 页指针 | 失败率 80~100% → 0~10%（10 次 × 3 轮） | 李振炜 |
| `etcd-4997/` | etcd#4997 | `consistentIndex` 无同步读写 | RACE 20/20 → 0/20 | 吴德诚 |
| `grpc-1667/` | grpc#1667 | `ccBalancerWrapper.subConns` 无同步 map | RACE ×3 → PASS ×3 | 李振炜 |
| `grpc-1687/` | grpc#1687 | 重复 `WriteStatus` → send on closed channel | FAIL(panic) ×3 → PASS ×3 | 李振炜 |
| `grpc-1546/` | grpc#1111 / PR #1546 | 并发 `WriteStatus` 越过状态检查 → send on closed channel | FAIL(panic) ×3 → PASS ×3 | 许汝轩 |
| `kubernetes-9926/` | k8s#9926 | 全局 `capabilities` 指针无同步读写 | RACE 20/20 → 0/20 | 吴德诚 |
| `moby-28682/`† | moby#28682 | `select` 在 ready 与 `ctx.Done` 同时就绪时随机选，漏发 close stdin | 漏发 85~105/200 → 0/200 | 李振炜 |
| `kubernetes-36377/`† | k8s#36377 | store 返回共享指针，reconcile 直接改，读者并发访问同一 map | annotations 1→2（污染）→ 恒为 1 | 李振炜 |
| `cockroachdb-17112/`† | crdb#17112 | 锁内决策、锁外读 `mu.files`，快照与决策时刻不一致 | 约 210 次/2s → 0 | 李振炜 |

† 这 3 条全部是 **minimal** 形态，没有 real-repo 证据：`moby-28682` 要跑着的 containerd，
两条 k8s / crdb 分别要活的控制面与 cgo + RocksDB。本机 `-race` 不可用
（`go build -race` 能过，产物启动即 `0xC0000139`），所以竞争类改用可观测不变量判定。
原因与替代方案见 [`real-repo-notes.md`](real-repo-notes.md) 第五节。

`moby-2d21996/` 也在本目录，但它**不在论文 41 条集合内**（171 条总表内，`reproduced` 为空），
不计入上面的 10 条。

## 两人各做了一遍的两条

`boltdb#341` 与 `grpc#1424` 李振炜、许汝轩都独立做过。合并规则是**保留两套证据、不取其一**：
各自的日志放在同一目录下并标出来源（`logs/` 与 `logs/xu/`，或 `boltdb_341_*` 与 `b2_*`），
README 里写清两边用的工具链和判定。两条的现象与结论一致，正好互为交叉验证。

## 目录内约定

| 路径 | 内容 |
|---|---|
| `README.md` | 症状、机理、修复、判定口径、实测、怎么重跑 |
| `code/` | 触发程序 / 探针 / 补丁（有的 case 保留完整工程：`cmd/`、`internal/`、`scripts/`） |
| `buggy/`、`fixed/` | 补充 7 条用这套双侧布局：两侧各一个 `main.go`，同一个驱动分别编译运行，代替 `code/` |
| `logs/` | buggy 与 fixed 两侧的原始输出 |
| `results/verdict.txt` | 两侧失败计数 + `REPRODUCED` / `NOT REPRODUCED` / `INCONCLUSIVE` |
| `shots/` | 终端截图（有则放） |
| `run.sh` | 一条命令跑完两侧（全部 case 都有；`RUNS=10 bash run.sh` 可改轮数） |
