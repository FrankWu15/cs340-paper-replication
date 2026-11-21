# 5 检测器评测（Table 8）

> 状态：未开始

要做的：

- deadlock detector：只看运行时 `all goroutines are asleep - deadlock!` 有没有打印
- `-race`：每个 bug 跑 100 次，统计检出率与「第几次检出」

样本准备：用 P4 已复现的阻塞类 case（`grpc-793`、`grpc-1293`、`grpc-1424`）作分母，
声明缩小规模。

注意：概率型 bug 单次跑不出不代表检不出，样本量不足时结论只能写方向一致。
