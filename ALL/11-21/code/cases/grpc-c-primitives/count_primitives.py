#!/usr/bin/env python3
"""count_primitives.py — 统计 gRPC-C（C/C++ 实现）的并发原语使用点。

论文 §3.2 的对照实验：
    "gRPC-C only uses lock, and it is used in 746 places (5.3 primitive usages
     per KLOC). gRPC-Go uses eight different types of primitives in 786 places
     (14.8 primitive usages per KLOC)."

论文只给了 746、140K 两数和 5.3 的密度，没写统计规则。本脚本把规则写成可复核的：

    范围    src/core/ + include/            （只算 C core，不含 php/ruby 等语言绑定）
    排除    third_party/ *.py *.rb 等非 C/C++ 文件
    计数    以下三类**调用点**各计一次，函数声明/定义不计：
              gpr_mu_lock()  gpr_mu_unlock()  gpr_mu_trylock()
            ——与 Go 侧 goast 的 lock_calls 同口径：.Lock 与 .Unlock 都算，
              因为论文 Table 4 的 Mutex 列也是按调用点计（P2 阶段已验证）。

    另外附带统计（不进 746）：gpr_mu_init/destroy（对象生命周期，不是使用点）、
    gpr_cv_*（条件变量，论文明确说 gRPC-C "only uses lock"，故不计入类型数）。

用法：
    python count_primitives.py --root /path/to/grpc --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

C_EXTS = (".c", ".cc", ".cpp", ".h", ".hpp")
SKIP_DIRS = {"third_party", ".git", "node_modules"}

# 调用点 = 函数名后面跟可选的空白再跟左括号；前面不能是标识符字符
CALL = {
    "mu_lock": re.compile(r"(?<![A-Za-z0-9_])gpr_mu_lock\s*\("),
    "mu_unlock": re.compile(r"(?<![A-Za-z0-9_])gpr_mu_unlock\s*\("),
    "mu_trylock": re.compile(r"(?<![A-Za-z0-9_])gpr_mu_trylock\s*\("),
    "mu_init": re.compile(r"(?<![A-Za-z0-9_])gpr_mu_init\s*\("),
    "mu_destroy": re.compile(r"(?<![A-Za-z0-9_])gpr_mu_destroy\s*\("),
    "rwlock_rdlock": re.compile(r"(?<![A-Za-z0-9_])gpr_rwlock_rdlock\s*\("),
    "rwlock_wrlock": re.compile(r"(?<![A-Za-z0-9_])gpr_rwlock_wrlock\s*\("),
    "rwlock_unlock": re.compile(r"(?<![A-Za-z0-9_])gpr_rwlock_unlock\s*\("),
    "cv_wait": re.compile(r"(?<![A-Za-z0-9_])gpr_cv_wait\s*\("),
    "cv_signal": re.compile(r"(?<![A-Za-z0-9_])gpr_cv_signal\s*\("),
    "cv_broadcast": re.compile(r"(?<![A-Za-z0-9_])gpr_cv_broadcast\s*\("),
}

# 函数定义/声明行形如 `void gpr_mu_lock(gpr_mu* mu) {` 或 `GPRAPI void gpr_mu_lock(...)`
DECL = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)+[*\s]*gpr_mu_(?:lock|unlock|trylock)\s*\(")


def code_lines(text: str) -> tuple[int, int]:
    """返回 (代码行, 原始行)。注释与空行不计，与 02_static_metrics.py 同规则。"""
    code, raw, in_block = 0, 0, False
    for line in text.splitlines():
        raw += 1
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
    return code, raw


def count_file(path: Path) -> tuple[dict, int, int]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}, 0, 0
    hits = {}
    for name, rx in CALL.items():
        n = len(rx.findall(text))
        if n:
            hits[name] = n
    # 头文件里的函数声明不算调用点：形如 `GPRAPI void gpr_mu_lock(gpr_mu* mu);`
    if path.suffix in (".h", ".hpp"):
        decl = sum(1 for line in text.splitlines()
                   if DECL.match(line) and line.rstrip().endswith(";"))
        if decl:
            hits["_decl_skipped"] = decl
    code, raw = code_lines(text)
    return hits, code, raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--subdirs", nargs="*", default=["src/core", "include"])
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    total = {k: 0 for k in CALL}
    code_total = raw_total = files = 0
    per_dir: dict[str, int] = {}

    for sub in args.subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(C_EXTS):
                    continue
                p = Path(dirpath) / fn
                hits, code, raw = count_file(p)
                if not hits and not code:
                    continue
                files += 1
                code_total += code
                raw_total += raw
                for k, v in hits.items():
                    if k in total:
                        total[k] += v
                per_dir[sub] = per_dir.get(sub, 0) + sum(
                    v for k, v in hits.items() if k in total)

    decl_skipped = 0
    for sub in args.subdirs:
        for p in (root / sub).rglob("*.h"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            decl_skipped += sum(1 for line in text.splitlines()
                                if DECL.match(line) and line.rstrip().endswith(";"))

    usage = total["mu_lock"] + total["mu_unlock"] + total["mu_trylock"]
    locks_all = usage + total["rwlock_rdlock"] + total["rwlock_wrlock"] + total["rwlock_unlock"]
    version = ""
    try:
        version = subprocess.run(["git", "-C", str(root), "describe", "--tags", "--always"],
                                 capture_output=True, text=True).stdout.strip()
    except OSError:
        pass

    out = {
        "root": str(root),
        "version": version,
        "subdirs": args.subdirs,
        "files": files,
        "code_lines": code_total,
        "raw_lines": raw_total,
        "kloc_code": round(code_total / 1000.0, 1),
        "kloc_raw": round(raw_total / 1000.0, 1),
        "counts": total,
        "lock_usage": usage,          # 论文 746 的对应量
        "lock_usage_all": locks_all,  # 含 rwlock
        "per_kloc_code": round(usage / (code_total / 1000.0), 2) if code_total else None,
        "per_kloc_raw": round(usage / (raw_total / 1000.0), 2) if raw_total else None,
        "header_decls_skipped": decl_skipped,
        "per_dir_usage": per_dir,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
