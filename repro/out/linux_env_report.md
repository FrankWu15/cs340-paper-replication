# Linux 环境验收报告

生成时间: 2026-10-25 16:06:15 UTC

| 检查项 | 实际值 | 期望 | 结论 |
|---|---|---|---|
| 发行版 | `Ubuntu 18.04.6 LTS` | Ubuntu 18.04 | ✅ |
| 内核 | `4.15.0-213-generic` | 4.15.x（soft） | ℹ️ |
| cgroup 版本 | `tmpfs` | tmpfs = v1 | ✅ |
| iptables | `iptables v1.6.1` | (legacy) | ✅ |
| gcc | `7` | >= 5 | ✅ |
| CPU 核数 | `4` | 4（固定） | ✅ |
| 内存 | `7 GB` | 8 GB | ✅ |

## Go 工具链

```
/usr/local/go1.10.8 → go version go1.10.8 linux/amd64
/usr/local/go → go version go1.27.3 linux/amd64
```

## 切换方式

```bash
go110   # Go 1.10.8，GOPATH 模式（编 2018 年快照代码）
go127   # Go 1.27.3，module 模式（编 goast、做现代对照）
```

## 关键参数

```
vm.max_map_count = 262144
fs.file-max      = 1048576
ulimit -n (当前) = 1024
swap             = 4.0G
时区             = 
```

## 复现链路自检

跑完下面两条，能通过就说明 P4 的地基是通的：

```bash
source /etc/profile.d/go-repro.sh && go110
cd $GOPATH/src/github.com/boltdb/bolt && go test ./...
CGO_ENABLED=1 go test -race ./...    # -race 需要 gcc，验证 P5 可行
```
