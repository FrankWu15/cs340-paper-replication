# moby#17176 —— devmapper 漏解锁

**状态：待并入。**

材料目前在 `1240012557/`（朱奕铭）：`Reproduction/`、`Screenshot/`、
`Source_comparison/` 三部分。并入时把复现代码放本目录，截图放
`results/shots/moby-17176_*.png`，源码对比表放 `docs/`。

症状：`devmapper` 设备在错误路径上未释放 `sync.Mutex`，后续调用全部阻塞。
