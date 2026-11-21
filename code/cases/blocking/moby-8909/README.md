# docker#8909 —— 持锁时调用会再次加锁的取值方法

| 项 | 值 |
|---|---|
| 类型 | blocking / shared_memory |
| 修复 commit | `03ea2166b66632ee7cdd824d7acd87b15c9bccb2`（Fix deadlock in ps exited filter） |
| 形态 | minimal（按原调用序列重实现） |
| 判定 | buggy 3/3 DEADLOCK，fixed 0/3 |

## 1. 症状

`docker ps -a --filter exited=0` 不返回，daemon 端无输出、CPU 不涨，
SIGQUIT 栈停在 `sync.(*Mutex).Lock` 上。

## 2. 机理

`daemon/list.go` 的 `Containers()` 在遍历容器时已经持有该容器的锁，
过滤器里又要拿退出码：

```go
for _, code := range filt_exited {
    if code == container.GetExitCode() {   // GetExitCode 内部 container.Lock()
```

而 `GetExitCode()` 自己先加锁再读字段。`sync.Mutex` 不可重入，同一个 goroutine
第二次 Lock 就永久阻塞。本目录的 `buggy/main.go` 保留了这条调用序列：
`Daemon.List` 持锁 → 调 `Container.GetExitCode()` → 再次 Lock。

## 3. 修复

上游补丁只改一行：调用方已持锁，就直接读字段。

```diff
-  if code == container.GetExitCode() {
+  if code == container.ExitCode {
```

`fixed/main.go` 与 buggy 的唯一差别就是这一行。

## 4. 判定口径

`List()` 放在 goroutine 里跑，主 goroutine 等 3 秒：

- 3s 内返回 → `VERDICT: OK`
- 超时 → `VERDICT: DEADLOCK`，退出码 2

## 5. 实测

各 3 轮：buggy 3/3 卡死（均满 3s），fixed 3/3 正常返回 `[zero1 zero2]`。
原始输出见 `logs/`，汇总见 `results/verdict.txt`。

## 6. 怎么重跑

```bash
bash run.sh
```

单文件、无外部依赖，`go build` 即可。Go 1.27 / windows-amd64。

## 7. 真实源码复现（VMware 虚拟机）

上面是 minimal 形态。在 Ubuntu 18.04 虚拟机上，这条已经改成**直接执行上游 `Daemon.Containers()`**：

```bash
bash run_real.sh          # 两侧各 3 轮，需要虚拟机环境
```

- buggy = `4d4a7b81`（修复提交 `03ea2166` 的父提交），fixed = `03ea2166`
- 驱动 `zz_repro_exited_test.go` 写在 `package daemon` 里，用真实 `contStore`、
  真实 sqlite `graphdb`、真实 `filters.FromParam` 组出 `Daemon`，然后调 `d.Containers(job)`
- 工具链：Go 1.5.4；`GOPATH=<repo>/vendor:<repo 父目录>`；
  `-tags "exclude_graphdriver_btrfs exclude_graphdriver_devicemapper"`

结果：buggy 3/3 超时，fixed 3/3 返回。超时时的栈（`logs/real/buggy_run1.log`）：

```
sync.(*Mutex).Lock
  daemon.(*State).GetExitCode        daemon/state.go:128
  daemon.(*Daemon).Containers.func2  daemon/list.go:102
  daemon.(*Daemon).Containers        daemon/list.go:152
```

即 `list.go:71` 拿的锁被 `list.go:102` 的 `GetExitCode()` 再拿一次。日志在 `logs/real/`，
环境与坑见 [`real-repo-notes.md`](../../real-repo-notes.md)。
