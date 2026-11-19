# 构建环境与源码来源

## 源码

| 侧 | 目录 | 提交 | 来源 |
|---|---|---|---|
| 缺陷版 | `$HOME/grpc1546/buggy` | `cf79c849790fd644fab2ef0996e07c177f7b689c` | 修复提交的第一父提交，`run.sh` 按提交号下载完整树 |
| 修复版 | `$HOME/grpc1546/fixed` | `22c3f92f5faea8db492fb0f5ae4daf0d2752b19e` | 修复提交完整树，同样按提交号下载 |

下载走 `https://codeload.github.com/grpc/grpc-go/tar.gz/<sha>`，解包后核对文件哈希才继续：

| 文件 | sha256 |
|---|---|
| buggy `transport/handler_server.go` | `221095b5340a5a222b135d6dd7b6d1829b495f7ac344b3859f765e47671a94ee` |
| fixed `transport/handler_server.go` | `e31892c63815574b668597cbbea2f623bc3f9a70256dff0b600e6a55ed2b663e` |
| 两侧 `transport/handler_server_test.go`（补丁后） | `efa63412682bbdda47677d07faaed9a1a13aea4d18f9bb63904ede8adf6ec6f8` |

`run.sh` 把实际提交号写进源码目录的 `.src_sha`，并把两侧 `handler_server.go`、测试文件、
`go.mod`、`go.sum` 的 sha256 记进 `logs/env.txt`；目录内容与提交对不上时直接报错，
不会拿本机残留目录凑数。官方补丁与提交元数据见 `patches/1546.patch`。

## 工具链

| 项 | 值 |
|---|---|
| 系统 | WSL2，Ubuntu 22.04.5，内核 6.18.40.1-microsoft-standard-WSL2 |
| Go | 1.22.9（`/usr/local/go-versions/go1.22.9/bin/go`） |
| 依赖管理 | module 模式（源码写于 2017 年，早于 go.mod，构建时补 `go.mod`/`go.sum`） |
| 并发核数 | 12（`nproc`） |

## 依赖锁定

```
module google.golang.org/grpc

go 1.22.9

require (
	github.com/golang/protobuf v0.0.0-20170808021621-1909bc2f63dc
	golang.org/x/net v0.0.0-20170809000501-1c05540f6879
	google.golang.org/genproto v0.0.0-20170731182057-09f6ed296fc6
)

require golang.org/x/text v0.0.0-20170730040918-3bd178b88a81 // indirect
```

与既有 `grpc-1424` 案例使用同一组版本（2017 年 8 月），两侧完全一致，唯一变量是
`handler_server.go` 中 `streamDone` 的置位位置。

## 环境变量

```bash
export GO111MODULE=on
export GOFLAGS=-mod=mod
export GOPROXY=https://goproxy.cn,direct
export GOSUMDB=off          # 2017 年的 pseudo-version 无法通过校验库验证
export GOPATH=$HOME/go
export GOMODCACHE=$HOME/go/pkg/mod
```

`GOPATH` / `GOMODCACHE` 必须显式设置：本机 `go env` 里残留过 `GOPATH=/root/go`
（早前以 root 运行留下的配置），普通用户直接跑会报
`could not create module cache: stat /root/go/pkg/mod: permission denied`。

## 构建要点

- 不要在 `/tmp` 下构建，本机 `/tmp` 会被定期清理，依赖解析状态可能中途丢失。
- Go 1.22 对 2017 年的测试文件会报 vet 错误（`conversion from untyped int to string`），
  所有命令都带 `-vet=off`。
- 缺陷版没有回归测试，只应用 `patches/1546-test.patch`；产品代码一行未改。
- `-count=1` 时两侧各 20 次全部通过，判定统一用 `-count=200` 在同一进程内重复；
  `200` 是选定的重复预算，不保证每轮必中，按轮统计。原因与实测见 `README.md` 的「判定口径」一节。
