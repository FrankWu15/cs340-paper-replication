# moby#0d9e543 — `Stop()` 持锁再调 `Kill()`，同一把 Mutex 重入自锁

## 元信息

| 项 | 值 |
|---|---|
| 论文 uid | `docker@0d9e5436`（注意：`@` 分隔、全小写，join 前需归一化） |
| 行为分类 | blocking（论文 `cause_group = shared_memory`） |
| 修复 commit | `0d9e54367f7bf7da9670de723d533eaa920868c8` |
| buggy 版本 | `9c3d2b6a4ed46eb3549416ceffd61683ad0a8efe`（fix 的父提交） |
| 真实源文件 | `container.go`（2013 年的 moby，包在仓库根目录） |
| 论文集合 | **不在 41 条复现集合内**（在 171 条总表内，`reproduced` 字段为空） |
| 原包环境 | 未标注 Go 版本；源码年代 2013-04 |
| 复现形态 | 最小复现（stdlib 模拟加锁结构），非完整 Docker 服务 |

## 1 症状

容器停止超时后，`Stop()` 走强制路径调 `Kill()`，而 `Kill()` 又要取同一把容器状态锁——`sync.Mutex` 不可重入，调用方 goroutine 永久阻塞。表现为"强制杀容器"这一步卡死，进程不再推进。

## 2 机理

`Stop()` 整段持 `container state mutex`，超时分支里调的是**导出的** `Kill()`：

```go
// Stop() 已持有 c.mu
if err := container.WaitTimeout(10 * time.Second); err != nil {
    log.Printf("Container %v failed to exit within 10 seconds of SIGTERM - using the force", container.Id)
    if err := container.Kill(); err != nil {   // ← Kill() 内部再 c.mu.Lock()
        return err
    }
}
```

`Kill()` 的第一件事就是 `c.mu.Lock()`（`code/moby_0d9e543.go:22-25` 保留了这一结构）：

```go
func (c *Container) Kill() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.kill()
}
```

同 goroutine 二次加锁 → 永久阻塞。修复把它换成不取锁的内部 `kill()`。

## 3 修复

上游只改一行（`results/source_comparison/container.diff`）：

```diff
-		if err := container.Kill(); err != nil {
+		if err := container.kill(); err != nil {
```

`kill()` 是内部方法、不取锁，因此不会重入。

## 4 判定口径（**两侧用的是不同证据，不能混说**）

这条 case 里有两个程序，各自回答一个不同的问题：

| 程序 | 回答什么 | 判定 |
|---|---|---|
| `code/moby_0d9e543.go` | 这个加锁结构会不会把 `Stop()` 卡死 | buggy：2s watchdog 到期打印 `Operation timed out after 2 seconds (lock blocked)`；fixed：打印 `Result: Completed successfully` |
| `detector/runtime_deadlock.go` | 这条 bug 的形态能不能被 Go 内置检测器抓到 | 打印 `fatal error: all goroutines are asleep - deadlock!`，exit 2 |

⚠️ **为什么必须分成两个程序**：`code/moby_0d9e543.go` 的 `runCase()` 里有 `case <-time.After(2 * time.Second)`。这个 pending timer 会让 `runtime.checkdead()` 认为"进程还可能被唤醒"，**内置检测器永远不会触发**。所以带 watchdog 的版本只能给 TIMEOUT 证据，DEADLOCK 证据只能来自 `detector/runtime_deadlock.go`——那里主 goroutine 连续两次 `mu.Lock()`，没有任何 timer 与后台协程，条件才成立。

这不是本 case 的缺陷，而是 P5 已经量化的普遍现象：`minimal` 复现体越"干净"越容易被检测器抓到，真实服务进程几乎抓不到（见 `docs/P5-CHECKLIST.md` §2）。写报告时要把这两条证据分开引用，不能把 `detector/runtime_deadlock.go` 的检出算成"这条 Docker bug 被检测到"。

### 4.1 实测（2026-11-21 本机复核）

Go 1.27.3 windows/386，`./run.sh` 退出码 0：

| 项 | 结果 |
|---|---|
| `code/moby_0d9e543.go` buggy 侧 | `Operation timed out after 2 seconds (lock blocked)` — **TIMEOUT** |
| `code/moby_0d9e543.go` fixed 侧 | `[kill] Executing internal kill without acquiring the lock` → `Completed successfully` — **CLEAN** |
| `detector/runtime_deadlock.go` | `fatal error: all goroutines are asleep - deadlock!`，栈顶 `sync.(*Mutex).Lock` ← `main.main`，**exit 2** |

完整输出见 `logs/repro.log`、`logs/detector.log`、`logs/verdict.txt`。

## 5 怎么重跑

```bash
cd code/cases/blocking/moby-0d9e543
./run.sh
```

产物：`logs/repro.log`、`logs/detector.log`（两侧完整输出）、`logs/verdict.txt`（`repro=... detector=...`）。

## 6 保真说明与边界

- `code/moby_0d9e543.go` 与 `detector/runtime_deadlock.go` 是原包 `reproduction_code/` 下的两个文件，**文件名与内容均逐字未改**，只调整了所在目录。
- 它复现的是 `Stop()→Kill()→mu.Lock()` 这条**加锁调用链**，不是完整 Docker 容器生命周期：没有 containerd、没有真实进程、没有 10s 超时等待。
- **完整 Docker 测试套件未执行**：2013 年的 moby 依赖 legacy 系统依赖与容器基础设施，超出单机范围。原包 `test_summary.txt` 第 4 项也记为 `NOT RUN`。
- **上游没有针对性回归测试**：原包检查了 `container_test.go`，未发现覆盖该死锁场景的用例（`NO DEDICATED REGRESSION TEST FOUND`）。因此本 case 只能靠自建最小程序判定，无法用官方测试做 buggy/fixed 对照——这一点与 `grpc-793` 那类"补丁自带测试"的 case 不同，报告里要注明。
- 原始英文说明与实验结果留在 `logs/original-README.md`、`logs/raw-test-summary.txt`，未经改写。
