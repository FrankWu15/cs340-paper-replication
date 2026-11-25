# docker#28682 —— ready 与 ctx.Done 同时就绪，select 随机丢掉 close stdin

| 项 | 值 |
|---|---|
| 类型 | non-blocking / message_passing |
| 修复 commit | `4e262f63876018ca78d54a98eee3f533352b0ac9` |
| 形态 | minimal（复刻 start() 里的双 case select） |
| 判定 | buggy 3/3 BUG（85~105/200），fixed 0/3 |

## 1. 症状

容器启动后立刻停止时，stdin 有时没有被关闭。表现为集成测试偶发失败，
重跑就过，属于典型的 flaky。

## 2. 机理

`libcontainerd/container_unix.go` 的 `start()`：

```go
go func() {
    select {
    case <-ready:
        ctr.sendCloseStdin()
    case <-ctx.Done():
    }
}()
```

容器很快就绪（ready 关闭）又立刻被停止（ctx 取消）时，两个 case 同时可执行。
Go 的 select 在多 case 就绪时**等概率随机**选一个，选中 `ctx.Done()` 就跳过
`sendCloseStdin()`。

## 3. 修复

补丁改成两段式：先等任一事件，再单独判断 ready 是否已就绪
（已关闭的 channel 永远可读，`default` 兜底）：

```go
select {
case <-ready:
case <-ctx.Done():
}
select {
case <-ready:
    ctr.sendCloseStdin()
default:
}
```

## 4. 判定口径

跑 200 轮，每轮 `close(ready)` 后立刻 `cancel()`，统计 `sendCloseStdin` 未被调用的次数：

- 漏发 > 0 → `VERDICT: BUG`（退出码 3）
- 漏发 == 0 → `VERDICT: OK`

期望值：buggy 约 50%（两 case 等概率），fixed 恒 0。

## 5. 实测

buggy 三轮分别漏发 85、105、98 / 200；fixed 三轮均 0/200。
与「等概率随机」的预测一致。

## 6. 怎么重跑

```bash
RUNS=5 bash run.sh
```

单文件、无外部依赖。

## 7. 竞争检测（2026-11-25，Ubuntu 18.04 虚拟机）

本机 Windows 上 `-race` 产物启动即 `0xC0000139`（缺 race 运行时 DLL），此前一直没跑检测器。
2026-11-25 在虚拟机 `ubuntu1804-p4`（Ubuntu 18.04.6 / go1.27.3 / gcc 7.5 / 4 核）上补跑：

| 段 | 设置 | 结果 |
|---|---|---|
| 不变量 | 不带 `-race`，10 轮/侧 | buggy 10/10 BUG（漏发 88~115 / 200），fixed 0/10 |
| 竞争检测 | `-race`，100 轮/侧，`GORACE=halt_on_error=1` | **buggy 0/100，fixed 0/100** |

0/100 是正确结果，不是检测失败：本缺陷是 `select` 在两个 case 同时就绪时等概率随机，
`stdinClose` 全程受 mutex 保护，没有任何未同步访问，ThreadSanitizer 没有可报的目标。
这正是论文「并非所有非阻塞型缺陷都是数据竞争」那条原因的实例。

重跑：`CASES=moby-28682 RUNS=10 RACE_RUNS=100 bash ../run_race.sh`
逐轮日志见 `logs/vm-1125/`，汇总见 `results/vm-1125.txt`。
