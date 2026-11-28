# boltdb#341 的 `-race` 实测（2026-11-28 · VM）

环境：Ubuntu 18.04.6 / 4 核 / **go1.10.8 linux/amd64** / gcc 7.5.0
commit：buggy `55af28c` vs fixed `c69cb102`

## 三套探针

| 探针 | 做什么 | 用途 |
|---|---|---|
| **A** 原样 | 开写事务 → `Close()` → 看它是否提前返回（不 Commit） | 与既有判定对齐 |
| **B** 并发 Put | 主 goroutine 循环 `b.Put`，另一路 `Close()` | 让两者在时间上重叠 |
| **C** Close 后 Commit | `Close()` 与写事务重叠后**继续 Commit** | bolt 的 `Put` 只写内存 node，Commit 才落 mmap —— 真正撞 munmap 的路径 |

## 结果（2 侧 × 3 探针 × 3 轮 = 18 次运行）

| 探针 | buggy | fixed |
|---|---|---|
| A | `race=0`，`VERDICT=BUG close_returned_early closeMs=0` ×3 | `race=0`，`VERDICT=OK close_waited closeMs=160` ×3 |
| B | `race=0`，`puts≈97–100 万`，**不崩** ×3 | `race=0`，`puts≈109–136 万` ×3 |
| C | `race=0`，**SIGSEGV ×3** | `race=0`，`COMMIT_OK` + `CLOSE_DONE` ×3 |

**0 条 `WARNING: DATA RACE`。**

C 探针 buggy 崩溃栈（`C_buggy_run1.log`）：

```
Tx.Commit → Bucket.spill → Cursor.search → Bucket.pageNode
    bolt/bucket.go:692   （读已被 Close munmap 的页）
```

## 判定

`-race` **未检出**（0/9 buggy 轮次）。原因：

1. 它是**对象生命周期 / 内存映射**问题，不是"两条内存访问缺 happens-before"；
2. `munmap` 不在 TSan 的插桩范围，进程先 SIGSEGV，来不及输出报告。

因此本 case 在 Table 12 记「实测、未检出」，凭据是"Close 提前返回 / Commit SIGSEGV"，与检测器无关。

## 复跑

```bash
bash scripts/run_341_race.sh     # A/B 探针
bash scripts/run_341_race_C.sh   # C 探针
```

两者都读 `$HOME/gopath/src/github.com/boltdb/bolt`，结果写 `$HOME/repro1128/11-28/boltdb341-race/`。
