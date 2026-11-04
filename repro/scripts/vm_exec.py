#!/usr/bin/env python3
"""在复现用 Linux 虚拟机（VMware + Ubuntu 18.04）上执行命令、传输文件。

依赖: paramiko（已装在 C:\\Users\\Li\\.workbuddy\\binaries\\python\\envs\\default）

用法:
    python vm_exec.py "uname -a"                 # 执行命令
    python vm_exec.py "sudo apt update"          # sudo 自动应答密码
    python vm_exec.py --put local.txt /tmp/x.txt # 上传
    python vm_exec.py --get /tmp/x.txt local.txt # 下载
    python vm_exec.py --py                        # 探测环境（简报）

环境变量（均有默认值）:
    VM_HOST  默认 192.168.47.128
    VM_USER  默认 li
    VM_PASS  默认取 ~/.vm_pass 文件内容
    VM_KEY   默认 ~/.ssh/id_repro

设计说明:
  - 用密钥认证，密码仅在 sudo 时需要，因此脚本内不回显、不落盘。
  - sudo 通过 `sudo -S` 从 stdin 读密码，免去 tty 依赖。
  - 免密 sudo 已通过 /etc/sudoers.d/90-li-nopasswd 配置，正常情况无需密码。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

import paramiko


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


HOST = env("VM_HOST", "192.168.47.128")
USER = env("VM_USER", "li")
KEY = os.path.expanduser(env("VM_KEY", "~/.ssh/id_repro"))


def load_password() -> str:
    if "VM_PASS" in os.environ:
        return os.environ["VM_PASS"]
    f = pathlib.Path.home() / ".vm_pass"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""


class VM:
    def __init__(self, timeout: float = 15.0) -> None:
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = dict(
            hostname=HOST, username=USER, port=22, timeout=timeout,
            allow_agent=False, look_for_keys=False,
        )
        if os.path.exists(KEY):
            kwargs["key_filename"] = KEY
        else:
            kwargs["password"] = load_password()
        self.client.connect(**kwargs)

    def close(self) -> None:
        self.client.close()

    def run(self, cmd: str, timeout: float = 1800.0) -> tuple[int, str, str]:
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        try:
            if self.client._transport and self.client._transport.is_active():
                stdin.write(load_password() + "\n")
                stdin.flush()
        except Exception:
            pass
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        return stdout.channel.recv_exit_status(), out, err

    def put(self, local: str, remote: str) -> None:
        """用 base64 走 stdin 写文件，避开 SFTP 子系统可能不可用的问题。"""
        import base64
        data = pathlib.Path(local).read_bytes()
        payload = base64.b64encode(data).decode("ascii")
        cmd = f"mkdir -p $(dirname {remote}) && base64 -d > {remote}"
        stdin, stdout, stderr = self.client.exec_command(cmd)
        stdin.write(payload)
        stdin.channel.shutdown_write()
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            raise RuntimeError(f"put failed: {stderr.read().decode('utf-8', 'replace')}")

    def get(self, remote: str, local: str) -> None:
        import base64
        rc, out, err = self.run(f"base64 -w0 {remote}")
        if rc != 0:
            raise RuntimeError(f"get failed: {err}")
        pathlib.Path(local).write_bytes(base64.b64decode(out.strip()))


PROBE = r"""
set +e
echo "host:      $(hostname)"
echo "kernel:    $(uname -r)"
echo "release:   $(. /etc/os-release; echo $PRETTY_NAME)"
echo "cgroup:    $(stat -fc %T /sys/fs/cgroup)  (tmpfs = v1)"
echo "iptables:  $(iptables --version 2>/dev/null)"
echo "tz:        $(cat /etc/timezone 2>/dev/null)"
echo "nofile:    $(ulimit -n)"
echo "cpu:       $(nproc)"
echo "mem:       $(free -m | awk '/^Mem:/{printf "%dGB", $2/1024}')"
echo "go1.10.8:  $(/usr/local/go1.10.8/bin/go version 2>/dev/null | awk '{print $3}')"
echo "go1.27.3:  $(/usr/local/go/bin/go version 2>/dev/null | awk '{print $3}')"
echo "gopath:    $(ls -d /opt/gopath/src/*/* 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="VM 远程执行工具")
    ap.add_argument("cmd", nargs="?", help="要执行的命令")
    ap.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"))
    ap.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"))
    ap.add_argument("--py", action="store_true", help="打印环境简报")
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    vm = VM()
    try:
        if args.put:
            vm.put(args.put[0], args.put[1])
            print(f"[put] {args.put[0]} -> {args.put[1]}")
            return 0
        if args.get:
            vm.get(args.get[0], args.get[1])
            print(f"[get] {args.get[0]} -> {args.get[1]}")
            return 0
        rc, out, err = vm.run(PROBE if args.py else (args.cmd or "true"), args.timeout)
        sys.stdout.write(out)
        if err.strip():
            sys.stderr.write(err)
        return rc
    finally:
        vm.close()


if __name__ == "__main__":
    raise SystemExit(main())
