# 2 方法

> 状态：草稿，素材齐

## 2.1 环境固定

不是按日期切分支——`git rev-list --before` 是开区间，会多出 3~41 个 commit。
做法是沿 first-parent 回退，找 `rev-list --count` 与论文表格数字**正好相等**的提交。
6 个仓库全部对齐后写进 `data/repo.lock.tsv`，`make check-pins` 可随时校验。

详见 `docs/p0-env.md`。

## 2.2 静态统计口径

`code/tools/goast/main.go` 遍历 AST，数两类东西：`go` 关键字的创建点、
7 类并发原语（Mutex、RWMutex、chan、WaitGroup、Once、atomic、Cond）。
按 KLOC 归一化后与论文逐格比较。

详见 `docs/p2-static.md`。

## 2.3 复现流程

每条 bug 五步：定位 buggy（`fix^1`）→ GOPATH 模式编译 → 按 bug report 触发 →
按症状判定（hang 用 SIGQUIT 打栈 / panic 看栈 / race 看报告）→ 重复 N 次统计。

驱动脚本 `code/harness/p4_case.sh`，判定分五态，详见 `code/harness/README.md`。
