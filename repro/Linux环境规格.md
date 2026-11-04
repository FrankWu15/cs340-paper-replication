# Linux 环境规格（P4 复现用）

> 目标：为 ASPLOS'19《Understanding Real-World Concurrency Bugs in Go》的 P4（bug 复现）与 P5（detector 评测）提供一台可重复、可回滚的 Linux 工作机。
> 配套脚本：`scripts/00_provision_linux.sh`（在 VM 内一键执行）

---

## 0. 先说一个必须写进报告的事实

**论文没有报告实验环境。** 全文（`out/paper_text.txt`）只写了：

> "To reproduce a bug, we rolled the application back to the buggy version, built the buggy version, and ran the built program using the bug-triggering input described in the bug report."

没有发行版、内核版本、Go 版本、CPU 核数、内存容量。这意味着**严格意义上的"环境级复现"是不可能的**，我们只能按代码时间线反推一个"最小惊讶"的环境。这一条要作为 threats to validity 写进复现报告。

反推依据：
- 数据窗口末端 = 2018-05-21（artifact `bug table.xlsx` 的 Date 列）
- 当时 Docker CE 是 18.03，Kubernetes 是 1.10，etcd 3.3，CockroachDB 2.0
- 这些项目的官方 CI 与文档在 2018 年上半年仍以 **Ubuntu 16.04** 为准

---

## 1. 发行版选择

### 结论

```
Ubuntu 18.04.6 LTS Server (64-bit, bionic)
```

### 为什么不选 16.04

16.04（xenial）确实更贴近 2018-05 的真实 CI 环境，但：

- 标准支持 2021-04 结束，ESM 于 **2026-04-30 到期**，现已完全 EOL
- apt 源已从 `archive.ubuntu.com` 迁至 `old-releases.ubuntu.com`，且不再有任何安全更新
- 安装 `build-essential`、`docker-ce` 时需要手工改源，过程中极易踩坑

对复现实验来说，**能稳定装软件**比**版本年份精确**更重要。

### 为什么 18.04 是安全的

| 特性 | 18.04 实际值 | 对 2018 年代码的意义 |
|---|---|---|
| 内核 | 4.15 | Docker 17.x/18.x 的 overlay2、cgroup 接口全部可用 |
| cgroup | **v1**（`/sys/fs/cgroup` 是 tmpfs） | K8s 1.10 只支持 v1；v2 会直接不认 |
| iptables | **legacy**（20.04 起换 nft） | Docker 17/18 写的 nft 规则会导致容器无网络 |
| glibc | 2.27 | Go 1.10 的 `-race` 与 cgo 正常 |
| systemd | 237 | kubelet 的 cgroup driver 可用 |
| gcc | 7.5 | 编译老 cgo 代码/CGO 依赖足够 |

ESM 至 2028-04，`archive.ubuntu.com/ubuntu/dists/bionic` 仍然在线。

### 镜像下载

- 官方：`https://releases.ubuntu.com/18.04/ubuntu-18.04.6-server-amd64.iso`
- 国内：`https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/18.04/ubuntu-18.04.6-server-amd64.iso`

选 **Server 版而不是 Desktop**：桌面环境会常驻 GNOME、tracker、gnome-software 等进程，在跑并发 bug 实验时干扰 CPU 调度，并且多消耗 1.5 GB 内存。操作通过 SSH 完成即可。

---

## 2. VMware 侧配置

创建虚拟机时按这个填：

| 项 | 值 | 说明 |
|---|---|---|
| 客户机操作系统 | Linux → Ubuntu 64 位 | |
| CPU | **4 核，1 个插槽** | 不要给 8 核。核数越多 race 窗口越小但单轮耗时越长；1–2 核很多 race 根本跑不出来。**固定分配，不要用"自动"** |
| 内存 | **8 GB**（宿主 ≥16 GB 时） | K8s 组件约 2 GB，CRDB 单节点 2–4 GB，Go 编译峰值 2–3 GB |
| 磁盘 | **100 GB**，SCSI，**不预分配**，存于 SSD | 6 个仓库完整克隆约 8 GB，Go build cache 2–5 GB，Docker 镜像 10 GB |
| 网络 | NAT | 单机复现足够；CRDB 多节点用同机不同端口 |
| 虚拟化引擎 | ✅ 勾选"虚拟化 Intel VT-x/EPT" | 仅在需要 Docker-in-Docker 或嵌套 kind/minikube 时必需 |
| 显示 | 关闭 3D 加速 | 无桌面，用不上 |
| 共享文件夹 | **不要开** | `vmhgfs` 编译极慢，等同 WSL 的 `/mnt/c` 问题 |

### 装之前必须确认：Hyper-V 已关闭

上一步你装了 WSL（会启用 `VirtualMachinePlatform`）。**如果 Hyper-V 系功能还开着，VMware 会退回 ULM（User Level Monitor）模式，性能下降一个量级。** 在管理员 PowerShell 里查：

```powershell
systeminfo | Select-String "Hyper-V"
```

如果出现"已检测到虚拟机监控程序。将不显示 Hyper-V 所需的功能"，说明 Hyper-V 在运行。需要关闭：

```cmd
dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart
dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart
bcdedit /set hypervisorlaunchtype off
```

然后**完全关机重启**（不是重启，是关机再开）。

---

## 3. 系统内配置（脚本自动完成）

`scripts/00_provision_linux.sh` 会做这些事，每步都幂等，可重复执行：

| 步骤 | 内容 | 原因 |
|---|---|---|
| 1 | 校验发行版是 bionic | 版本不对直接退出，避免后面白做 |
| 2 | apt 源换清华镜像 | 官方源在国内装 200+ 个包要几十分钟 |
| 3 | 装 `build-essential git curl gdb strace sysstat pkg-config libc6-dev` | `-race` 需要 gcc；`strace`/`gdb` 是分析卡死的关键工具 |
| 4 | 装 **Go 1.10.8** → `/usr/local/go1.10.8` | 2018 年代码的原始工具链，GOPATH 模式 |
| 5 | 装 **Go 1.27.3** → `/usr/local/go` | 编译 goast 静态分析器、做"现代 Go 是否修复了这些 bug"的对照实验 |
| 6 | 写 `/etc/profile.d/go-repro.sh` | 提供 `go110` / `go127` 两个切换函数 |
| 7 | `vm.max_map_count=262144`、`fs.file-max=1048576` | etcd/CRDB 的 mmap 与文件描述符需求 |
| 8 | `nofile` 上限 1M | 并发实验会瞬间打开大量 fd |
| 9 | 时区设为 UTC | 日志时间戳与 bug report 对比时不产生时区偏移 |
| 10 | 关闭 `unattended-upgrades`、`apt-daily` | 防止半夜自动升级内核，把环境改坏 |
| 11 | 启用 VMware 时间同步 | 见下节，**这一条对复现率影响最大** |
| 12 | 输出 `linux_env_report.md` | 记录内核/cgroup/Go/gcc/nproc/内存，供报告引用 |

手工要做的只有两件：**跑脚本前打一个干净快照，跑完再打一个 `base-ready` 快照**。

### 为什么时间同步非做不可

论文里相当一部分 blocking bug 的触发条件是 `time.After` / `context.WithTimeout` 到期。VM 挂起恢复后，客户机时钟与宿主 RTC 会产生偏移（VMware 默认把 `time.synchronize.*` 设成 FALSE 以省开销）。时钟一漂，超时判定的时刻跟着漂，同一程序 10 轮的复现率就会飘忽不定，直接污染 Table 8 的统计。

脚本会执行：

```bash
vmware-toolbox-cmd timesync enable
```

并建议在 VM 设置里勾选 "Synchronize guest time with host"。

---

## 4. Go 版本矩阵

| 用途 | 版本 | 安装路径 | 模式 |
|---|---|---|---|
| 编译 2018 年快照代码（moby/k8s/etcd/crdb/grpc-go/bolt） | **1.10.8** | `/usr/local/go1.10.8` | GOPATH（`GO111MODULE=off`） |
| 编译 `tools/goast`、跑现代对照 | **1.27.3** | `/usr/local/go` | module |

切换方式（脚本已写入 profile）：

```bash
go110      # GOROOT=/usr/local/go1.10.8, GO111MODULE=off
go127      # GOROOT=/usr/local/go, 默认
go version # 确认当前实际版本，逐 bug 记录到 repro.csv
```

**每个 bug 的复现记录里必须写清实际用的 Go 版本**，否则复现率不可解释——有些 bug 在 Go 1.12 之后因为调度器改动就再也复现不出来。

Go 1.10 **没有 module 支持**，只能用 GOPATH。仓库路径必须是：

```
$GOPATH/src/github.com/moby/moby
$GOPATH/src/k8s.io/kubernetes
$GOPATH/src/github.com/coreos/etcd
$GOPATH/src/github.com/cockroachdb/cockroach
$GOPATH/src/google.golang.org/grpc
$GOPATH/src/github.com/boltdb/bolt
```

注意 etcd 的导入路径在 2018 年是 `github.com/coreos/etcd`（不是现在的 `go.etcd.io/etcd`），放错目录会编译失败。脚本的 `--with-repos` 会按正确路径克隆。

---

## 5. 装完验收

在 VM 里逐条跑，全部符合才算环境就绪：

```bash
lsb_release -ds                    # Ubuntu 18.04.6 LTS
uname -r                           # 4.15.x
stat -fc %T /sys/fs/cgroup         # tmpfs（= cgroup v1）
iptables --version                 # (legacy)，不能出现 nf_tables
gcc --version | head -1            # 7.5.0
nproc                              # 4
free -g | awk '/Mem/{print $2}'    # 8

go version                         # go1.27.3 linux/amd64
go110 && go version && cd $GOPATH/src/github.com/boltdb/bolt && go test ./... 2>&1 | tail -3
```

最后一条能通过，说明 Go 1.10.8 + GOPATH + 老代码这条链路是通的——这是 P4 的地基。

再验证 `-race`：

```bash
cd $GOPATH/src/github.com/boltdb/bolt
go110 && CGO_ENABLED=1 go test -race ./... 2>&1 | tail -5
```

`-race` 需要 `CGO_ENABLED=1` 和 gcc，能编译出带检测器的测试二进制就说明 P5 可行。

---

## 6. 快照策略

按这个顺序打三个快照，出问题能精准回退，不用重装：

| 快照名 | 时机 | 用途 |
|---|---|---|
| `00-clean` | 系统装完、脚本执行前 | 环境被改坏时回到这里 |
| `01-base-ready` | 脚本执行完、验收通过 | **日常起点**，P4 每轮实验从这里开 |
| `02-per-app` | 每个 app 的依赖装完后 | moby/k8s/crdb 的依赖互相冲突时隔离用 |

并发 bug 复现要反复切 Go 版本、改 sleep、重编，没有快照的话一天能重装三次系统。

---

## 7. 磁盘与网络注意

- **不要在 `/mnt/hgfs`（共享文件夹）里编译**，也**不要用 NFS 挂 Windows 目录**。编译 K8s 这种量级会慢 5–10 倍，而且 inotify 事件会丢。
- 代码放 VM 内部的 `/opt/gs`（和 Windows 侧 `C:\gs` 对应，路径短、全 ASCII）。
- 完整克隆 6 个仓库约 8 GB、耗时 20–60 分钟，受代理影响。可以先只拉 boltdb + grpc-go + etcd 三个小的（约 180 MB）把流程跑通，moby/k8s/crdb 后续按需补。

---

## 8. 与 Windows 侧的分工

| 任务 | 在哪做 | 原因 |
|---|---|---|
| artifact 解析、统计、画图（P1/P2/P6） | Windows | 已跑通，与平台无关 |
| goast 静态分析 | Windows | 已编译验证 |
| `-race` detector 评测（P5） | **两边都行** | Go 支持 `windows/amd64` 的 race detector，但 Linux 结果更接近论文环境，建议以 Linux 为准 |
| 老版 Docker / K8s / CRDB 整套启动（P4） | **只能 Linux** | 需要 cgroup v1、iptables legacy、systemd |
| 纯 Go 项目的单元测试（boltdb/etcd/grpc-go） | 两边都行 | 优先 Linux，便于统一口径 |
