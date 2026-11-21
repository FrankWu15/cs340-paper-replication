# boltdb · beginTx 错误分支漏解锁导致的死锁

> 数据集里没有 issue 编号，按数据集路径记为 `blocking-bugs/boltdb/defdb743c…`。

| 项 | 值 |
|---|---|
| 分类 | **blocking**（死锁） |
| 仓库 | `github.com/boltdb/bolt` |
| buggy 提交 | `01bc9be72f46f0f1978b1f1581440c399b3a7684` |
| 修复提交 | `defdb743cdca840890fea24c3111a7bffe5cc0a3`（"Fix deadlock on remmap."） |
| 检测手段 | Go 内置死锁检测器（`fatal error: all goroutines are asleep - deadlock!`） |
| 判定 | buggy **deadlock** / fixed **正常返回 `ErrDatabaseNotOpen`** |
| 负责 | 许汝轩 1240011357 |

## 症状

`beginTx()` 先拿 mmap 读锁、再拿 meta 锁；数据库已关闭时走错误分支，只释放了
`mmaplock` 而漏掉 `metalock`：

```go
db.mmaplock.RLock()
db.metalock.Lock()
if !db.opened {
    db.mmaplock.RUnlock()
    return nil, ErrDatabaseNotOpen   // ← 漏了 db.metalock.Unlock()
}
```

第一次 `Begin` 泄漏写锁，第二次 `Begin` 卡在 `db.go:349` 的 `Mutex.Lock`，运行时
判定全体 goroutine 休眠，报死锁退出（exit 2）。修复就是在错误分支补上
`db.metalock.Unlock()`。

## 判定口径

| 侧 | 现象 |
|---|---|
| buggy | `fatal error: all goroutines are asleep - deadlock!`，栈停在 `db.go:349` |
| fixed | 第 2 次 `Begin` 于 85ns 返回 `database not open`，未卡死 |

## 证据

| 文件 | 内容 |
|---|---|
| `logs/b3_buggy_closed.log` | buggy 侧死锁栈（`DB.beginTx` → `db.go:349`） |
| `logs/b3_fixed_closed.log` | fixed 侧两次 `Begin` 都正常返回错误 |
| `logs/b3_buggy_remap.log` / `b3_fixed_remap.log` | **附实验**：并发压测 8s / 800+ 次写入，两侧均未卡死 |
| `code/main.go` | 触发程序（`runClosed` 走错误分支，`runRemap` 走压测分支） |
| `code/README-upstream.md` | 原始记录：机理、提交、可靠性说明 |
| `patches/03-begin-lock-leak.patch` | 修复提交原文 |

## 已知限制

修复提交的说明写的是 remap 路径死锁，但该路径在 `01bc9be7` 这个快照上压不出来
（附实验两侧都未卡死）。实际复现成立的是**同一提交修复的错误分支漏解锁**，栈与
`db.go:349` 完全对得上。`logs/b3_*_remap.log` 保留了失败的尝试，没有当作成功证据。

## 重跑

环境：Linux + **Go 1.6.4**，GOPATH 模式（这批代码早于 go.mod）。

```bash
GOROOT=/usr/local/go-versions/go1.6.4 \
GOPATH=<独立 gopath> go run code/main.go
```

两个版本的源码快照分别放在独立 GOPATH 下，避免互相污染；下载与切换步骤见
`report/appendix/xu-1357-report.md` 第 8 节。
