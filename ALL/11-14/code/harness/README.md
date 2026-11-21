# harness —— 复现驱动脚本

所有脚本都假设仓库在 `$GOPATH/src` 下（2018 年前的代码没有 go.mod）。Go 版本按被测项目选，
`p4_*.sh` 默认钉 `GOROOT=/usr/local/go1.10.8`。

## 通用复现驱动

| 脚本 | 用途 | 用法 |
|---|---|---|
| `p4_case.sh` | **A 档**：用补丁自带的官方测试判 buggy/fixed | `p4_case.sh <repo> <fix_sha> <test_regex> <pkg> [iters=3] [timeout=30]` |
| `p4_probe.sh` | **B 档**：注入自写探针，两侧只换被测源码；支持 `-race` | `p4_probe.sh <repo> <fix_sha> <pkg> <test_regex> <probe_dir> [iters] [timeout] [race\|norace]` |
| `p4_deps.sh` | 把 2018 年前后的依赖（x/net、protobuf、glog 等）拉进 GOPATH | `p4_deps.sh` |
| `p4_grpc_logs.sh` | 批量跑四条 grpc 官方测试并归档日志 | `p4_grpc_logs.sh` |

`p4_case.sh` 的关键行为：buggy 侧 checkout `fix^` 后**只应用补丁里 `*_test.go` 的部分**，
非测试代码保持 buggy —— 否则测的就是修复版了。

两个环境变量：

```bash
# 测试包自己的 flag 必须放在 -args 之后
P4_EXTRA_ARGS="-args -only_env=tcp-clear" bash p4_case.sh ...
# 把「RPC 卡到测试自身 deadline」也算命中（grpc#1850 用）
P4_DEADLINE_HIT=1 bash p4_case.sh ...
```

判定口径（五态）：`PASS` / `FAIL` / `TIMEOUT` / `NOTRUN` / `ERROR`，另加 `DEADLINE`（需显式开启）。
`NOTRUN` 专指 `-run` 正则没匹配到任何测试却仍输出 `ok` 的情况——**不能当作通过**，
grpc#1687 第一次跑就栽在这上面（包目录填成了 `test`，实际在 `transport`）。

## 单条 bug 专用

| 脚本 | 用途 |
|---|---|
| `08_repro_boltdb.sh` | boltdb 两条（`#341`、`7fb06fee`）的探针 + 10 轮统计 |
| `00_setup_repos.sh` / `00_pin_exact.sh` | 拉 6 个上游仓库并钉到论文 commit |
| `xu_boltdb_setup.sh` / `xu_boltdb_run.sh` | 许汝轩那套 boltdb 复现（Go 1.6.4，两个 bug 共用） |
| `run.sh` / `Makefile` | 上层封装：`make check-pins`、批量跑等 |

## 环境模板

`local.env` 是路径覆盖模板（`REPO_ROOT`、`GO_MODERN`/`GO_LEGACY` 等），
`_paths.sh` 会在环境变量之后读它。默认值不填也能跑，只要仓库在 `$GOPATH/src` 下。
