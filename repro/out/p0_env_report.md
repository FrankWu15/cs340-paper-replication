# P0 环境与数据准备报告

生成时间：2026-11-04 13:44

## 工具链

| 用途 | 路径 | 版本 |
|---|---|---|
| 现代（编译 goast / 对照实验） | `C:\gs\toolchain\go1.27.3\go\bin\go.exe` | go version go1.27.3 windows/amd64 |
| 旧版（编译 2015–2018 老代码） | `C:\gs\toolchain\go1.10.8\go\bin\go.exe` | go version go1.10.8 windows/amd64 |
| 机器原有（32 位，仅记录） | `C:\Program Files (x86)\Go\bin\go.exe` | go version go1.27.3 windows/386 |

> 机器原有的 Go 是 **windows/386（32 位）**，不支持 `-race`，P5 无法用它做检测器评测。
> 已额外准备 amd64 版本，不改动原有安装。

## 仓库快照（切点 2018-05-21）

| 项目 | commit | 日期 | commit 数 | 论文 | 差异 | 克隆方式 |
|---|---|---|---|---|---|---|
| boltdb | `fd01fc79c553` | 2018-03-02 | 816 | 816 | +0 ✅ | 完整 1.9M |
| etcd | `346589edd1dc` | 2018-05-21 | 14101 | 14101 | +0 ✅ | 完整 126M |
| grpc-go | `f66923519395` | 2018-05-21 | 2528 | 2528 | +0 ✅ | 完整 49M |
| docker | `9bd5d9912f0c` | 2018-05-22 | 35149 | 35149 | +0 ✅ | treeless（仅 commit） 91M |
| cockroachdb | `cc4511e1be86` | 2018-05-22 | 29485 | 29485 | +0 ✅ | treeless（仅 commit） 88M |
| kubernetes | `1f0d9505790c` | 2018-05-22 | 65684 | 65684 | +0 ✅ | treeless（仅 commit） 72M |

已获取 6 / 6 个仓库，其中 6 个 commit 数与论文一致。

### 切点是怎么精确对齐到论文的

`--before=DATE` 是左闭右开：`--before=2018-05-21` 得到「截至 5-20 结束」的计数，`--before=2018-05-22` 才是「含 5-21 全天」。论文的值落在两者之间，说明作者的取样时点是 2018-05-21 当天某个时刻。

因此用 `scripts/00_pin_exact.sh` 从 5-21 上界沿 first-parent 回溯，逐步算 `rev-list --count`，定位到计数与论文完全相等的 commit：

| 项目 | 5-21 上界 | 回溯前计数 | 精确定位 commit | 计数 | 论文 | 方式 |
|---|---|---|---|---|---|---|
| boltdb | `fd01fc79c553` | 816 | `fd01fc79c553` | 816 | 816 | 精确命中 |
| etcd | `7940113906db` | 14107 | `346589edd1dc` | 14101 | 14101 | 精确命中 |
| grpc-go | `c16e07b13065` | 2531 | `f66923519395` | 2528 | 2528 | 精确命中 |
| docker | `da99009bbb11` | 35160 | `9bd5d9912f0c` | 35149 | 35149 | 精确命中 |
| cockroachdb | `7c7818fd6d8e` | 29526 | `cc4511e1be86` | 29485 | 29485 | 精确命中 |
| kubernetes | `e85b81bbee09` | 65725 | `1f0d9505790c` | 65684 | 65684 | 精确命中 |

## artifact 数据表

- `bugs_master.csv`：171 条 bug（blocking 85 / non-blocking 86）
- 其中有独立补丁：169 条
- 作者标记为已复现（Reproduced?=1）：44 条
