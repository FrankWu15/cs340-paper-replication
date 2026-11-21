# P3 动态测量（Table 3）

> 状态：未开始

## 计划

- 负载：gRPC 官方 benchmark 的 unary / streaming / async 三种
- Go 侧：`runtime/trace` 统计 goroutine 创建与销毁，算生命周期
- C 侧：`/proc/<pid>/task` 采样线程数
- 对比：同一负载下 goroutine 数与线程数、归一化后的耗时

## 要证的结论

goroutine 数明显多于线程数，但归一化耗时更短。

## 风险

gRPC benchmark 依赖 2018 年的版本，与当前工具链可能不兼容，需要单独固定环境。
