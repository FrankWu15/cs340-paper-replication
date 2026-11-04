#!/usr/bin/env python3
"""P2 阶段：调用 tools/goast 统计一个仓库的 goroutine 创建点与并发原语用量，
并做 KLOC 归一化，输出可作为论文 Table 2 / Table 4 一行的结果。

用法:
    python scripts/02_static_metrics.py --repo vendor/etcd --app etcd \
        --out out/static_etcd.json

前置: 需要 Go 工具链（go run），或先 `cd tools/goast && go build -o ../../bin/goast`
     然后用 --goast-cmd 指向编译好的二进制，避免每个仓库都重新编译。
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent
# 在 repro/ 目录下执行，保证 go.mod 生效（tools/goast 只用标准库）
DEFAULT_GOAST = "go run ./tools/goast"


def run_goast(cmd: str, repo: Path, include_tests: bool, skips: list[str],
              include_vendor: bool = False) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    args = shlex.split(cmd) + ["-root", str(repo), "-json", str(tmp)]
    if include_tests:
        args.append("-include-tests")
    if include_vendor:
        args.append("-include-vendor")
    for s in skips:
        args += ["-skip", s]

    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPRO))
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"goast 失败:\n{proc.stderr.strip()}")
    data = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)
    return data


def count_code_lines(path: Path) -> int:
    """近似 cloc 的「代码行」：跳过空行、纯注释行，以及块注释跨行。"""
    code = 0
    in_block = False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if in_block:
            if "*/" in s:
                in_block = False
                rest = s.split("*/", 1)[1].strip()
                if rest and not rest.startswith("//"):
                    code += 1
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            else:
                rest = s.split("*/", 1)[1].strip()
                if rest and not rest.startswith("//"):
                    code += 1
            continue
        if s.startswith("//"):
            continue
        code += 1
    return code


def count_kloc(repo: Path) -> tuple[float, float]:
    """统计 LOC 的两个口径，per-KLOC 用第一个。

    论文分母经反推可知是**全仓代码行**（含 vendor、含测试、去注释空行）：
    由 Table 2「创建点 / per-KLOC」可解出 Docker≈806K、etcd≈443K、K8s≈2322K；
    与本仓全仓原始行数之比稳定在 0.73~0.80，正是 cloc 的 code 行占原始行比例。
    若只算非 vendor 非测试的原始行，则相差 2~6 倍（见 out/table2_table4_compare.md）。

    返回 (代码行含vendor, 原始行不含vendor)。前者对齐论文，后者是旧口径。
    """
    if shutil.which("cloc"):
        proc = subprocess.run(
            ["cloc", "--json", "--quiet", "--include-lang=Go", str(repo)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                info = json.loads(proc.stdout)
                code = info.get("Go", {}).get("code", 0)
                if code:
                    return code / 1000.0, code / 1000.0
            except json.JSONDecodeError:
                pass

    code_all = 0
    raw_novendor = 0
    for p in repo.rglob("*.go"):
        if ".git" in p.parts:
            continue
        code_all += count_code_lines(p)
        if "vendor" not in p.parts and not p.name.endswith("_test.go"):
            try:
                raw_novendor += p.read_bytes().count(b"\n") + 1
            except OSError:
                pass
    return code_all / 1000.0, raw_novendor / 1000.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--out", required=True, help="输出 JSON")
    ap.add_argument("--goast-cmd", default=DEFAULT_GOAST)
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--include-vendor", action="store_true",
                    help="创建点/原语统计是否含 vendor（论文 LOC 分母含 vendor，分子是否含待核）")
    ap.add_argument("--skip", action="append", default=[], help="额外跳过目录，可重复")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"[x] 目录不存在: {repo}", file=sys.stderr)
        return 2

    print(f"[..] 统计 {args.app} ({repo})")
    counts = run_goast(args.goast_cmd, repo, args.include_tests, args.skip,
                       args.include_vendor)

    kloc, kloc_novendor = count_kloc(repo)
    kloc_src = "code_lines_incl_vendor"

    # 锁用机械口径 lock_calls：凡 .Lock/.Unlock/.RLock/.RUnlock 调用点都算，
    # 不依赖类型推断，可用 grep 逐仓库复核。counts["mutex"] 是严格口径，
    # 只认得清接收者的调用，对包装类型（如 CRDB 的 syncutil.Mutex）和内嵌 mutex 会低估。
    locks = counts.get("lock_calls") or counts["mutex"]
    sm = locks + counts["atomic"] + counts["once"] + counts["waitgroup"] + counts["cond"]
    chan_all = counts["chan_make"] + counts["chan_send"] + counts["chan_recv"]
    # 论文 Table 4 的 chan 列只算**收发**、不含 make：
    # 反推论文绝对值后，send+recv 在 boltdb 上精确等于 11、gRPC 176 vs 181、
    # K8s 698 vs 730、Docker 416 vs 393、etcd 863 vs 892，五个仓库吻合；
    # 计入 make 则系统性高出 25%。make 仅保留作诊断。
    chan = counts["chan_send"] + counts["chan_recv"]
    # 论文 Table 4 的 Misc 列 = sync.Pool（见 tools/goast 注释与 out/table2_table4_compare.md）。
    # context.* 数量极大且 etcd 该列为 0，不可能是论文口径，仅保留作诊断。
    misc = counts.get("misc_pool", 0)
    mp = chan + misc
    total = sm + mp
    gsites = counts["go_stmt_normal"] + counts["go_stmt_anonymous"]

    def pct(v: int) -> float:
        return round(100.0 * v / total, 2) if total else 0.0

    result = {
        "app": args.app,
        "repo": str(repo),
        "kloc": round(kloc, 1),
        "kloc_raw_novendor": round(kloc_novendor, 1),
        "kloc_source": kloc_src,
        "raw_counts": counts,
        # Table 2
        "goroutine_sites_total": gsites,
        "goroutine_sites_normal": counts["go_stmt_normal"],
        "goroutine_sites_anonymous": counts["go_stmt_anonymous"],
        "goroutine_sites_per_kloc": round(gsites / kloc, 3) if kloc else None,
        # Table 4
        "primitives_total": total,
        "shared_memory_pct": pct(sm),
        "message_passing_pct": pct(mp),
        "pct": {
            "lock_calls": pct(locks),
            "mutex_strict": pct(counts["mutex"]),
            "atomic": pct(counts["atomic"]),
            "once": pct(counts["once"]),
            "waitgroup": pct(counts["waitgroup"]),
            "cond": pct(counts["cond"]),
            "chan": pct(chan),
            "chan_make_diagnostic": counts.get("chan_make", 0),
            "misc": pct(misc),
            "misc_context_diagnostic": counts.get("misc_context", 0),
        },
        "primitives_per_kloc": round(total / kloc, 2) if kloc else None,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[ok] {args.app}: KLOC={result['kloc']}({kloc_src}) "
        f"goroutine 创建点={gsites} ({result['goroutine_sites_per_kloc']}/KLOC) "
        f"原语={total} 共享内存={result['shared_memory_pct']}% 消息传递={result['message_passing_pct']}%"
    )
    print(f"     -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
