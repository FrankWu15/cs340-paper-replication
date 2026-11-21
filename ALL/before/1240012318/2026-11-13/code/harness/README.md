# harness —— 复现驱动

三个脚本，都按"buggy / fixed 对照"跑，判定口径一致。

## p4_case.sh —— A 档：补丁自带测试

```
p4_case.sh <repo> <fix_sha> <test_regex> <pkg_subdir> [iters] [timeout_s]
```

buggy 侧取 `fix^1`，然后把修复提交里 `*_test.go` 的部分单独打上去（`git diff fix^1 fix -- '*_test.go'`），
产品代码保持 buggy。这样"测试是修复提交里的、被测代码是坏的"，判定才有意义。

## p4_probe.sh —— B 档：自写探针

```
p4_probe.sh <repo> <fix_sha> <pkg_subdir> <test_regex> <probe_dir> [iters] [timeout_s] [race|norace]
```

补丁里没有测试，所以探针自己写，放在 `code/cases/<case>/probe/*_test.go`，两侧都注入同一份，
只换被测源码。`race` 会加 `-race`，供数据竞态类 bug 使用。

与 `p4_case.sh` 相比多了两条判定：

- `WARNING: DATA RACE` 或 `fatal error: concurrent map ...` → **RACE**
- `no tests to run` → **NOTRUN**（探针没被编进包，结果无效，不能当 PASS）

## p4_deps.sh —— 依赖补齐

```
p4_deps.sh <repo> <pkg_subdir>
```

反复 `go test -c` 编译，把 `cannot find package` 的包 `go get -d` 回来。2018 年的 grpc-go
没有 go.mod，GOPATH 里缺依赖时用它补。

## 环境要求

```bash
export GOPATH=$HOME/gopath
export GO111MODULE=off
export GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH
```

`GOROOT` 必须显式钉住，否则交互式 shell 里预置的新版 Go 会让 1.10.8 的二进制去编译新版标准库，
报 `internal/goarch` 之类莫名其妙的错。
