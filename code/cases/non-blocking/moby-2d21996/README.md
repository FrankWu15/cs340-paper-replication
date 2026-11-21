# moby#16309 — `volumeStore` 的 `Count()` / `List()` 未加锁读共享 map

## 元信息

| 项 | 值 |
|---|---|
| 论文 uid | `Moby#16309`（注意：大写 `M`，与 `moby#17176` 的小写写法不一致，join 前需归一化） |
| 行为分类 | non-blocking（论文 `cause_group = shared_memory`） |
| 修复 commit | `2d21996eec8d3e6100f19fa0d0fa7adad25285ca`（`volumes: add synchronization to Count and List`） |
| buggy 版本 | `59311faaed4e3384fc8da738a57a25f17ae07e05`（fix 的父提交） |
| 真实源文件 | `daemon/volumes.go` |
| 论文集合 | **不在 41 条复现集合内**（在 171 条总表内，`reproduced` 字段为空） |
| 原包环境 | Ubuntu 22.04 / Linux amd64 / **Go 1.18.1** / `-race` |
| 复现形态 | 最小复现（stdlib 模拟 volumeStore），非完整 Docker 服务 |

## 1 症状

`volumeStore` 维护一个被 mutex 保护的 `vols` map。写侧（`Increment` / `Decrement`）**加锁**，读侧（`Count` / `List`）**不加锁**——同步策略不一致，并发下直接触发 data race。

两种表现：

| 模式 | 表现 |
|---|---|
| `count before` | race detector 报 `WARNING: DATA RACE`，冲突对是 `Increment()` 写 vs `Count()` 读 `volumeCounter.count` |
| `list before` | race detector 报 data race，**并且** runtime 报 `fatal error: concurrent map iteration and map write`——`List()` 遍历 map 时 `Increment()` 正在插入新 key |

`list` 这一条比单纯 data race 更严重：Go 的 map 并发迭代/写入是运行时直接 abort，不是"读到脏数据"那么温和。

## 2 机理

```go
func (s *volumeStore) Count(v volume.Volume) int {
	vc, exists := s.vols[v.Name()]   // ← 无锁读
	...
}

func (s *volumeStore) List() []volume.Volume {
	var ls []volume.Volume
	for _, vc := range s.vols {       // ← 无锁遍历
		ls = append(ls, vc.Volume)
	}
}

func (s *volumeStore) Increment(v volume.Volume) {
	s.mu.Lock()                       // ← 写侧加锁
	defer s.mu.Unlock()
	...
}
```

读侧不取锁时，`s.mu` 对它们不存在，锁只保护了写侧之间——典型的"半个锁"。

## 3 修复

上游给两个读方法补上同一把锁（`results/source_comparison/volumes.diff`，每个方法 +2 行）：

```diff
 func (s *volumeStore) Count(v volume.Volume) int {
+	s.mu.Lock()
+	defer s.mu.Unlock()
 	vc, exists := s.vols[v.Name()]
@@
 func (s *volumeStore) List() []volume.Volume {
+	s.mu.Lock()
+	defer s.mu.Unlock()
 	var ls []volume.Volume
```

注意这里是 `Lock()` 而非 `RLock()`：`s.mu` 是 `sync.Mutex`，没有读写之分。修复的语义是"把读也纳入同一把排他锁"，不是改成读写锁——报告里不要写成"加了读锁"。

## 4 判定口径

| 判定 | 条件 |
|---|---|
| RACE | 输出含 `WARNING: DATA RACE`（non-blocking 的主判据） |
| MAP_ABORT | 输出含 `concurrent map iteration and map write`（`list before` 的附加形态，同样算触发） |
| CLEAN | 输出含 `Test completed`，且无上述两者 |

`-race` 报告必须看**栈是否落在目标代码**。这条 case 的目标帧是 `volumeStore.Count` / `volumeStore.List` / `volumeStore.Increment`；如果只出现 `testing.(*common).FailNow` 这类框架帧，属于假阳性，不计入（`boltdb-7fb06fee` 就踩过，见 `docs/P5-CHECKLIST.md` §7）。

## 5 怎么重跑

```bash
cd code/cases/non-blocking/moby-2d21996
./run.sh
```

四个组合各产一份日志：`logs/{count,list}-{before,after}.log`，汇总在 `logs/verdict.txt`。

⚠️ **`-race` 需要 cgo/gcc**。Windows 本机会报 `0xc0000139`（缺运行时 DLL），必须在 Linux / WSL2 里跑。

### 5.1 复核状态

**本次整理未复核**（2026-11-21 虚拟机未开机）。下表是原包在 Ubuntu 22.04 / Go 1.18.1 下的结果，出自 `logs/raw-test-summary.txt`，未经本仓库重跑验证：

| 组合 | 迭代 | 原包结果 |
|---|---|---|
| `count before` | 100,000 | `WARNING: DATA RACE`，Found 1 data race，冲突对 `Increment` 写 vs `Count` 读 |
| `count after` | 100,000 | `Test completed`，无 race |
| `list before` | 100,000 | `WARNING: DATA RACE` + `fatal error: concurrent map iteration and map write` |
| `list after` | 10,000 | `Test completed`，无 race |

在补齐复核之前，报告里引用这些数字必须标注"原包结果，未独立复核"。

## 6 保真说明与边界

- `code/volume_race.go` 直接沿用原包 `reproduction_code/` 下的文件名，**逐字未改**：`before` / `after` 通过 `fixed bool` 参数切换，两侧共用同一份代码，避免"两个文件悄悄改出别的差异"。
- 复现的是 `Count`/`List` 的**加锁缺失**，不是完整 Docker volume 生命周期：没有 daemon、没有真实 volume driver。
- **迭代次数有历史偏差**：原包最初用 100,000 次，`list after` 太慢被中断，之后统一改为 10,000 次；历史结果表里记录的是当时实际用的次数（`logs/raw-test-summary.txt` 末尾有说明）。当前代码固定 10,000。
- 原包构建出的 `volume_race` 二进制（2.4MB）未纳入仓库——它可由 `run.sh` 重新构建，且属于构建产物。
- 原始英文说明与结果留在 `logs/original-README.md`、`logs/raw-test-summary.txt`，未经改写。
