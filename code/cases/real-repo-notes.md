# 真实源码复现：环境与方法（补充 7 条）

这份笔记写给 `blocking/moby-8909`、`blocking/moby-256`、`blocking/moby-27782` 三条——
它们是补充复现里唯一尝试过「直接跑上游源码」的。其余四条（`moby-28682`、`kubernetes-30872`、
`kubernetes-36377`、`cockroachdb-17112`）停在 minimal 形态，原因见本文第五节。

判定口径与仓库其它 case 一致：改的是「用谁的代码」，不是「怎么判定」。

| case | 形态 | 结果 |
|---|---|---|
| `blocking/moby-8909` | **real-repo**：`Daemon.Containers()` 原生执行 | 3/3 DEADLOCK vs 3/3 OK |
| `blocking/moby-256` | **real-repo**：上游 `archive.go` 原文件单独编译 | 3/3 DEADLOCK vs 3/3 OK |
| `blocking/moby-27782` | 尝试 real-repo，**结论不成立**（环境干扰） | 两侧都可能挂，不计入 |
| `non-blocking/moby-28682` | minimal | 需要跑着的 containerd |
| `blocking/kubernetes-30872` | minimal | 包能编译，但触发依赖活的联邦控制面 |
| `non-blocking/kubernetes-36377` | minimal | 需要 client-go 的 store 装配 |
| `non-blocking/cockroachdb-17112` | minimal | crdb 要 cgo + RocksDB，编不动 |

## 一、环境

| 项 | 值 |
|---|---|
| 机器 | VMware 虚拟机 `ubuntu1804-p4`，`li@192.168.47.128`（NAT） |
| 系统 | Ubuntu 18.04.6，内核 4.15.0-213，4 vCPU / 7 GB / 57 GB 可用 |
| 工具链 | Go 1.5.4（docker 1.3 时代）、Go 1.7.6（2016 年 dockerd） |
| 依赖 | `libdevmapper-dev`、`libsqlite3-dev`、`btrfs-tools`、gcc 7.5 |

`run_real.sh` 里的 `/home/li/...` 是这台虚拟机的路径，换机器要改。三个坑都是踩出来的：

1. **GitHub 直连被掐**。`git ls-remote` 偶尔能过，`git fetch` 稳定报
   `gnutls_handshake() failed`。改用 gitee 镜像按 SHA 浅拉：
   `git fetch --depth=1 https://gitee.com/mirrors/docker <sha>`，6 MB 就够。
   需要父提交时用 `--depth=2`——`--depth=1` 会把该提交标成 shallow，
   `git rev-parse <sha>^` 直接报 `unknown revision`。

2. **Go 1.4/1.5 时代的代码 + GCC 默认 PIE**。`ld: -r and -pie may not be used together`。
   `CC="gcc -no-pie"` 不管用（Go 1.5 按单命令处理），要写一个包装脚本再
   `CC=/home/li/bin/gcc-nopie`。

3. **docker 1.3 是 `vendor/src` 布局**，不是 Go 1.6+ 的 `vendor/`。
   `GOPATH=<repo>/vendor:<repo 的父目录>`；再配
   `-tags "exclude_graphdriver_btrfs exclude_graphdriver_devicemapper"`
   跳过两个跟新头文件不兼容的旧 cgo 驱动（`btrfs_ioctl_vol_args_v2`、
   `struct_dm_deps` 字段名变了）。

编译验证：`go build ./daemon` 5 秒出 2.1 MB 归档，说明整套 daemon 在这个工具链下是通的。

## 二、moby-8909 —— 真实 `Daemon.Containers()`

- buggy：`4d4a7b81`（修复提交 `03ea2166` 的父提交），fixed：`03ea2166`
- 驱动：`blocking/moby-8909/zz_repro_exited_test.go`，写在 `package daemon` 里，
  用真实的 `contStore`、真实 sqlite `graphdb`、真实 `filters.FromParam` 拼出一个 `Daemon`，
  然后**直接调 `d.Containers(job)`**，`daemon/list.go` 一行未改。

```bash
bash blocking/moby-8909/run_real.sh        # 两侧各 3 轮
```

结果（`blocking/moby-8909/logs/real/`）：

```
buggy run1-3: VERDICT: DEADLOCK  Daemon.Containers() did not return within 5s
fixed run1-3: VERDICT: OK (returned)
```

buggy 侧超时的真实栈（`logs/real/buggy_run1.log`）：

```
sync.(*Mutex).Lock(...)
  daemon.(*State).GetExitCode(...)        daemon/state.go:128
  daemon.(*Daemon).Containers.func2(...)  daemon/list.go:102
  daemon.(*Daemon).Containers(...)        daemon/list.go:152
```

即 `writeCont` 先拿 `container.Lock()`（`list.go:71`，锁的是内嵌 `*State` 的 `sync.Mutex`），
接着 exited 过滤器调 `container.GetExitCode()`，而 `(*State).GetExitCode` 内部再 `s.Lock()`。
`sync.Mutex` 不可重入，自锁。修复提交只把这一行改成读字段 `container.ExitCode`。

这是补充 7 条里唯一一条**上游函数本体被原样执行**的死锁，证据强度与 `etcd-*` 三条同级。

## 三、moby-256 —— 真实 `CmdStream`

- buggy：`1d6929c8`（修复提交 `58befe30` 的父提交），fixed：`58befe30`
- 2013 年的 `archive.go` 在仓库根、`package docker`，但 `CmdStream` 只依赖四个标准库包，
  所以可以**原文件单独编译**：`go test archive.go zz_repro_cmdstream_test.go`。
  文件是从 `git show <sha>:archive.go` 直接导出的，逐字节相同，没有改一行。
- 子进程：`sh -c 'head -c 1048576 /dev/zero 1>&2; echo done'`，
  先写满 64 KiB 的 stderr 管道再写 stdout。

```bash
bash blocking/moby-256/run_real.sh
```

```
buggy run1-3: VERDICT: DEADLOCK  CmdStream reader did not finish within 5s
fixed run1-3: VERDICT: OK (5 bytes, err=<nil>)
```

顺带一个细节：buggy 那版的注释里就写着
`// FIXME: can this block if stderr outputs more than the size of StderrPipe()'s buffer?`
——上游自己标了疑点，四年后才被这个 commit 修掉。

## 四、moby-27782 —— 试了，但结论不成立

- buggy：`6314bec`，fixed：`a69a59ff`
- 驱动：`blocking/moby-27782/zz_repro_followlogs_test.go`，用真实 `JSONFileLogger`
  写 8000 条记录、`ReadLogs{Follow:true}` 跟随、读一条后 `Close()`。

三次跑下来结果互相矛盾：先 1 次 buggy 挂 / fixed 通，再跑到 buggy 3/3 通、fixed 1/3 挂。
抓栈看到卡点在 `gopkg.in/fsnotify.v1.(*Watcher).Remove` 的 `sync.Cond.Wait`，
不在 `read.go:294` 的 `logWatcher.Msg <- msg`。

原因是 fsnotify v1 的 inotify 实现在这个内核上，`Remove` 会等事件协程，
而这个协程正是被 `followLogs` 卡住的那条——两边谁先卡是调度决定的，
和修不修无关。**因此这条的 real-repo 结论不可用**，仍以 minimal 版本为准，
日志留在 `blocking/moby-27782/logs/real/` 作为「试过但环境不成立」的留档。

换成 real-repo 那一栏时，这条**不计入**。

## 五、剩下四条为什么还是 minimal

| bug | 卡点 |
|---|---|
| `moby-28682` | `libcontainerd` 要连一个真在跑的 containerd，且要 grpc 会话；起 containerd 又是一层依赖 |
| `kubernetes-30872` | `federation/pkg/federation-controller/util` 能编（31 秒），但 `ClustersSynced` 里 `HasSynced()` 的重入是由活着的联邦控制面、经 `NotifyClusterUpdate` 触发的；自己塞一个会回锁的 stub controller，等于又造了一遍 minimal，只是换了个包名 |
| `kubernetes-36377` | 要在 `client-go` 的 `cache.Store` 上装 informer，再让 reconcile 改共享对象；装配量比 #30872 还大，同样要活的控制面 |
| `cockroachdb-17112` | crdb 依赖 cgo + RocksDB，2017 年的构建脚本还要 `make` 拉一大堆 C++；编不动 |

这四条在报告里如实写成「minimal 复现」，不算进 real-repo 那一栏。
