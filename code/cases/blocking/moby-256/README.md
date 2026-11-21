# docker#256 —— 先读完 stdout 再读 stderr，双管道互等

| 项 | 值 |
|---|---|
| 类型 | blocking / message_passing |
| 修复 commit | `58befe3081726ef74ea09198cd9488fb42c51f51` |
| 形态 | minimal（进程内起子进程复刻 CmdStream） |
| 判定 | buggy 3/3 DEADLOCK，fixed 0/3 |

## 1. 症状

`docker cp` / `docker export` 在容器命令往 stderr 输出较多时整个卡住，
既不报错也不结束。

## 2. 机理

`archive.go` 的 `CmdStream` 在同一个 goroutine 里顺序做两件事：

```go
_, err := io.Copy(pipeW, stdout)   // 先等 stdout EOF
errText, _ := ioutil.ReadAll(stderr)  // 之后才读 stderr
```

子进程若先往 stderr 写超过管道缓冲（Linux 64KB），写调用阻塞、进程不退出；
stdout 因此也不会 EOF，父进程卡在 `io.Copy`。两边互等。

本目录的复现不依赖 shell 的 `/dev/stderr`：程序以 `-child` 参数启动自身作为子进程，
子进程先写 1MB 到 stderr，再写 stdout。父进程按原顺序读，必然卡死。

## 3. 修复

补丁把 stderr 的读取挪到独立 goroutine，结果经 `errChan` 交给读 stdout 的那一侧：

```go
go func() { errText, _ := ioutil.ReadAll(stderr); errChan <- errText }()
go func() {
    io.Copy(pipeW, stdout)
    errText := <-errChan
    cmd.Wait()
    ...
}()
```

两个管道同时被消费，子进程永远不会因 stderr 写满而阻塞。

## 4. 判定口径

主 goroutine 用 5 秒等待 `io.Copy(io.Discard, out)` 完成：

- 完成 → `VERDICT: OK`
- 超时 → `VERDICT: DEADLOCK`（退出码 2）

## 5. 实测

buggy 3/3 满 5s 超时；fixed 3/3 在 1s 内读完（1MB stderr 全部被丢弃）。

## 6. 怎么重跑

```bash
bash run.sh
```

注意子进程用的是 `os.Executable()`，所以必须先 `go build`，不能只 `go run`。
`run.sh` 已经先编译再跑。

## 7. 真实源码复现（VMware 虚拟机）

上面是 minimal 形态。这条的真实版更简单，因为 2013 年的 `archive.go` 只依赖四个标准库包，
可以**原文件单独编译**：

```bash
bash run_real.sh          # 两侧各 3 轮，需要虚拟机环境
```

- 从 `git show <sha>:archive.go` 导出原文件（逐字节相同，未改一行），
  与驱动一起 `go test archive.go zz_repro_cmdstream_test.go`
- buggy = `1d6929c8`，fixed = `58befe30`；Go 1.5.4
- 子进程：`sh -c 'head -c 1048576 /dev/zero 1>&2; echo done'`，先写满 64 KiB stderr 再写 stdout

结果：buggy 3/3 满 5s 超时，fixed 3/3 返回 `5 bytes, err=<nil>`（即 `done\n`）。
buggy 那版源码里上游自己留了注释
`// FIXME: can this block if stderr outputs more than the size of StderrPipe()'s buffer?`，
说明这个疑点当年就被记下来了。日志在 `logs/real/`。
