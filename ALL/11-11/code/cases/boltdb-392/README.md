# boltdb#392 —— mmap 竞态

**状态：待并入。**

代码与实验目前在 `1240012684/`（吴德诚）：独立 Go module 工程，含 `harness/`、
`scripts/`、40 次试验的 `results/` 与 Dockerfile，可独立构建运行。

并入时需注意：该工程自带 `go.mod`，与其余 case 的 GOPATH 模式不同，
应整目录保留，不要打散成分析脚本。

症状：bolt 在 `mmap` 扩容与并发读之间缺少同步，读到半写的 meta 页。
