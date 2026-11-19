# 构建环境与源码来源

## 源码

| 侧 | 目录 | 提交 | 来源 |
|---|---|---|---|
| 缺陷版 | `$HOME/grpc1546/buggy` | `cf79c849790fd644fab2ef0996e07c177f7b689c` | 修复提交的第一父提交，按提交号下载完整树 |
| 修复版 | `$HOME/grpc1546/fixed` | `22c3f92f5faea8db492fb0f5ae4daf0d2752b19e` | 修复提交完整树 |

两侧源码与提交号的对应见上表；`run.sh` 会把修复提交号写进 `logs/env.txt`。
官方补丁与提交元数据分别见 `patches/1546.patch`、上游 `upstream-commit.json`（未随本目录入库）。

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
- `-count=1` 无法稳定触发，判定统一用 `-count=200`；原因与实测见 `README.md` 的「判定口径」一节。
