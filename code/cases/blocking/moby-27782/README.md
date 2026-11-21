# docker#27782 —— 关闭后仍强行送达最后一条消息

| 项 | 值 |
|---|---|
| 类型 | blocking / message_passing |
| 修复 commit | `a69a59ffc7e3d028a72d1195c2c1535f447eaa84` |
| 形态 | minimal（复刻 followLogs 的关闭时序） |
| 判定 | buggy 3/3 DEADLOCK，fixed 0/3 |

## 1. 症状

`docker logs --follow` 的客户端断开后，daemon 里负责跟随日志的协程不退出，
fsnotify watcher 一直挂着，反复 attach 会累积。

## 2. 机理

`daemon/logger/jsonfilelog/read.go` 的 `followLogs` 在发送消息时：

```go
select {
case logWatcher.Msg <- msg:
case <-logWatcher.WatchClose():
    logWatcher.Msg <- msg   // 关闭了也要把最后一条送到
    return errDone
}
```

`Msg` 是无缓冲 channel。消费者断开后不再接收，这一句永久阻塞；
又因为同一个 goroutine 卡在这里，后面的 `fileWatcher.Remove(name)` 也执行不到。

## 3. 修复

补丁引入 `context`：`WatchClose()` 收敛成 `ctx.Done()`，并起一个独立 goroutine
在被取消时做 `fileWatcher.Remove(name)`；发送侧改成 `case <-ctx.Done(): return errDone`，
不再强行送达。

## 4. 判定口径

消费者读两条后关闭 watcher 并停止接收，然后等 3 秒：

- `followLogs` 返回且 watcher 已移除 → `VERDICT: OK`
- 返回但 watcher 还在 → `VERDICT: BUG`（退出码 3）
- 3s 未返回 → `VERDICT: DEADLOCK`（退出码 2）

## 5. 实测

buggy 3/3 卡在 `Msg <- msg`；fixed 3/3 正常返回且 `Remove` 已调用。

## 6. 怎么重跑

```bash
bash run.sh
```

## 7. 真实源码复现：试过，结论不成立

在虚拟机上用真实 `JSONFileLogger` 试过一条驱动（`zz_repro_followlogs_test.go`）：
写 8000 条记录、`ReadLogs{Follow:true}` 跟随、读一条后 `Close()`，再看 reader 是否退出。

结果不稳定：一次是 buggy 挂 / fixed 通，再跑变成 buggy 3/3 通 / fixed 1/3 挂。
抓栈发现卡点在 `gopkg.in/fsnotify.v1.(*Watcher).Remove` 的 `sync.Cond.Wait`，
不在 `read.go:294` 的 `logWatcher.Msg <- msg`——fsnotify 的 inotify 实现在这个内核上，
`Remove` 要等事件协程，而那条协程正是被 `followLogs` 卡住的，谁先卡取决于调度，与修不修无关。

因此**这条仍以 minimal 版本为准**，real-repo 的日志留在 `logs/real/`，仅作为
「尝试过、环境不允许」的留档。
