# cockroachdb#17112 —— 锁内决策、锁外读文件列表

| 项 | 值 |
|---|---|
| 类型 | non-blocking / shared_memory |
| 修复 commit | `d5a604c99d9e9741f7f2242de204abde1b47c2d9` |
| 形态 | minimal（复刻 checkpoint 的 check-then-use） |
| 判定 | buggy 3/3 BUG（约 210 次 / 2s），fixed 0/3 |

## 1. 症状

backup 的 checkpoint 保存下来的文件列表，与「决定要 checkpoint 那一刻」的
文件集合不一致；同时 `mu.files` 在锁外被读，与导出协程的 append 构成数据竞争。

## 2. 机理

`pkg/ccl/sqlccl/backup.go`：

```go
doCheckpoint := timeutil.Since(mu.lastCheckpoint) > backupCheckpointInterval
if doCheckpoint { mu.lastCheckpoint = timeutil.Now() }
mu.Unlock()
... jobLogger.JobID() ...
if doCheckpoint {
    desc.Lock()
    desc.Files = append(backupFileDescriptors(nil), mu.files...)  // ← 锁外读 mu.files
}
```

决策用的是锁内时刻的文件数，真正拷贝时 `mu.files` 已经被其他导出协程追加过。
这是典型的 check-then-use：快照与决策点脱节，且读共享 slice 未加锁。

## 3. 修复

补丁把拷贝挪进锁内，锁外只用局部快照：

```go
s.mu.Lock()
var checkpointFiles []string
if time.Since(s.lastCheckpoint) > BackupCheckpointInterval {
    s.lastCheckpoint = time.Now()
    checkpointFiles = append([]string(nil), s.files...)
}
s.mu.Unlock()
if checkpointFiles != nil { desc.Files = checkpointFiles }
```

## 4. 判定口径

8 个导出协程持续 append；主协程 2 秒内反复 checkpoint。
每次 checkpoint 比较「拷贝到的长度」与「锁内决策时刻看到的长度」：

- 两者不等 → 记一次违规
- 违规 > 0 → `VERDICT: BUG`（退出码 3）

不用 `-race` 的原因同 k8s#36377：本机 race 运行时不可用；这里用可观测的
check-then-use 不一致替代。

## 5. 实测

buggy 三轮分别违规 212、208、218 次（2 秒窗口，决策时刻约 520 万个文件）；
fixed 三轮均 0 次。

## 6. 怎么重跑

```bash
bash run.sh
```

单文件、无外部依赖；跑满 2 秒后自行结束。
