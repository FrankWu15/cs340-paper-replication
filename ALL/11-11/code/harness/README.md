# harness —— 单条 bug 复现的通用驱动

四条脚本支撑所有 case，`code/cases/<case>/run.sh` 只是把参数固定下来的薄壳。

| 文件 | 作用 |
|---|---|
| `p4_case.sh` | 单条 bug 的 buggy / fixed 对照，五态判定 |
| `p4_deps.sh` | 循环编译探测缺哪个包并 `go get`，直到通过 |
| `p4_grpc_logs.sh` | 四条 grpc bug 一键跑完并按 bug 归集日志 |
| `08_repro_boltdb.sh` | boltdb 两条的批处理（含 341 的内联探针） |

## p4_case.sh

```bash
p4_case.sh <repo_dir> <fix_sha> <test_regex> <pkg_subdir> [iters] [timeout_s]
```

- `fix_sha` 用修复提交，buggy 侧自动取 `^1`；merge commit 也是 `^1`，即第一父
- `test_regex` 用 `^Name$`，不要省掉 `$`
- `pkg_subdir` 是测试相对仓库根的路径，仓库根填 `.`
- 只把补丁里 `*_test.go` 的部分 apply 到 buggy 侧，产品代码保持 buggy

输出两行 `SUMMARY`，格式 `pass=? fail=? timeout=? notrun=? error=?`。

## 三个必须记住的环境坑

**一、GOROOT 要显式钉住。** 虚机 `/etc/profile.d/go-repro.sh` 里默认
`GOROOT=/usr/local/go`（1.27），只改 PATH 不改 GOROOT，go1.10.8 的二进制会去读 1.27
的标准库，报 `internal/goarch` 之类根本对不上的包名，全部瞬间 FAIL。

**二、GOPATH 不能继承。** 同一个 profile 把 `GOPATH` 写成 `/opt/gopath`，而仓库在
`$HOME/gopath`。脚本里显式 `export GOPATH=$HOME/gopath`。

**三、换 commit 后必须 `rm -rf $GOPATH/pkg`。** GOPATH 模式下 `.a` 不会随 checkout
失效，会链接到上一个版本的代码，buggy 侧会跑出 fixed 的行为。

## 判定口径

| 状态 | 条件 |
|---|---|
| PASS | 以 `ok` 开头 |
| FAIL | 以 `FAIL` 开头 |
| TIMEOUT | 含 `test timed out` |
| NOTRUN | 含 `no tests to run` |
| ERROR | 其它（编译失败、依赖缺失） |

`go test` 在 `-run` 空匹配时仍然打印 `ok`。不单独识别 `NOTRUN`，就会把
「测试根本没跑」当成「复现成功」——这是本项目踩过的最贵的一个坑。
