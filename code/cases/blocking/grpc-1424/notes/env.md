# 构建环境记录

## 与 BoltDB 部分的差异

| 项 | BoltDB 部分 | gRPC-Go 部分 |
|---|---|---|
| Go 版本 | 1.6.4 | 1.22.9 |
| 依赖管理 | GOPATH 模式（无 go.mod） | module 模式（临时生成 go.mod） |
| 依赖来源 | 手工摆放源码至 `src/github.com/...` | 代理下载，版本固定至 2017 年 8 月 |
| 理由 | 源码为 2014 年提交，早于 go.mod 机制 | 见下 |

gRPC-Go 同样早于 go.mod 机制，但未采用 GOPATH 模式，原因有三：

1. 该快照依赖 4 个外部仓库，GOPATH 模式下需手工摆放 4 份源码并保证版本互相兼容，出错面更大；
2. 最新的 `golang.org/x/net` 已将最低 Go 版本要求提升至 1.26，直接 `go get` 无法解析，必须精确指定历史版本，而 module 模式对版本指定更直接；
3. 修复提交自带回归测试，测试文件本身无外部测试框架依赖，module 模式不会引入额外变量。

此差异属于构建手段不同，不影响前后对照的有效性：缺陷版与修复版使用完全相同的 `go.mod` / `go.sum` / Go 版本，唯一变量是那 9 行 `defer`（见 `source-diff.txt`）。

## 依赖版本

固定至修复提交的时间点（2017-08-04）附近，记录于 `01-lbwatcher-leak.go.mod`：

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

`go.sum` 副本见 `01-lbwatcher-leak.go.sum`，共 8 行。

## 环境变量

```bash
export GO111MODULE=on
export GOPROXY=https://goproxy.cn,direct
export GOSUMDB=off
export GOFLAGS=-mod=mod
export PATH=/usr/local/go-versions/go1.22.9/bin:$PATH
```

`GOSUMDB=off` 为必需：目标版本为 2017 年的 pseudo-version，校验数据库无法验证其哈希。

## 已知的操作性问题

- `go get <module>@<12位sha>` 对 `golang.org/x/text` 与 `google.golang.org/genproto` 会回退至 `golang.org` 直连，在本机网络环境下失败。必须手写完整的 pseudo-version（形如 `v0.0.0-20170731182057-09f6ed296fc6`，含时间戳与 12 位 sha 前缀）才能经代理解析。
- 构建工作目录不可置于 `/tmp`。本机 `/tmp` 会被定期清理，构建中途被清空会导致依赖解析状态丢失。当前工作目录为 `/home/xlm/grpctest`（修复版）与 `/home/xlm/grpcbuggy`（缺陷版）。

## 源码快照位置

```
/home/xlm/grpccases/leak/buggy/gopath/src/google.golang.org/grpc   缺陷版 39c8c386
/home/xlm/grpccases/leak/fixed/gopath/src/google.golang.org/grpc   修复版 4e56696c
```

两级目录名中的 `gopath` 为早期按 GOPATH 布局下载时的遗留，实际构建已改为 module 模式，目录名不影响结果，归档时未重命名。
