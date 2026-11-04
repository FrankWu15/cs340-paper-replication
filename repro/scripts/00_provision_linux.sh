#!/usr/bin/env bash
# ============================================================================
# 00_provision_linux.sh
#   在 Ubuntu 18.04 LTS 上准备「Go 并发 bug 复现」环境（P4/P5 用）
#
#   用法：
#     sudo bash 00_provision_linux.sh                 # 基础环境（推荐先跑这个）
#     sudo bash 00_provision_linux.sh --with-repos    # 额外克隆 6 个上游仓库
#     sudo bash 00_provision_linux.sh --swap-off      # 额外关闭 swap（跑 K8s 时必需）
#     sudo bash 00_provision_linux.sh --report /tmp/x.md
#
#   幂等：可重复执行，已完成的步骤会跳过。
# ============================================================================
set -euo pipefail

SNAP_DATE="2018-05-22"          # 取该日期之前的最后一个 commit（论文数据窗口末端 2018-05-21）
GO_OLD="1.10.8"
GO_NEW="1.27.3"
GO_DIR_OLD="/usr/local/go1.10.8"
GO_DIR_NEW="/usr/local/go"
GOPATH_DIR="/opt/gopath"
WORK_DIR="/opt/gs"
REPORT="./linux_env_report.md"
MIRROR_HOST="https://mirrors.tuna.tsinghua.edu.cn"
WITH_REPOS=0
SWAP_OFF=0
USE_MIRROR=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-repos) WITH_REPOS=1; shift ;;
    --swap-off)   SWAP_OFF=1; shift ;;
    --no-mirror)  USE_MIRROR=0; shift ;;
    --report)     REPORT="$2"; shift 2 ;;
    -h|--help)    sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

info()  { printf '\033[1;34m[>]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || die "请用 root 执行：sudo bash $0"

# ---------------------------------------------------------------------------
# 1. 发行版校验
# ---------------------------------------------------------------------------
CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-unknown}")"
info "检测到发行版代号: $CODENAME"
if [[ "$CODENAME" != "bionic" ]]; then
  warn "本项目以 Ubuntu 18.04 (bionic) 为目标环境。"
  warn "当前是 $CODENAME —— 若为 focal/jammy，iptables 已换成 nft、cgroup 转 v2，"
  warn "老版 Docker (17.x/18.x) 与 Kubernetes 1.10 大概率跑不起来。"
  read -r -p "仍然继续？[y/N] " ans || ans=""
  [[ "${ans,,}" == "y" ]] || exit 1
fi

# ---------------------------------------------------------------------------
# 2. apt 源
# ---------------------------------------------------------------------------
if [[ $USE_MIRROR -eq 1 && "$CODENAME" == "bionic" ]]; then
  if ! grep -q "tuna.tsinghua" /etc/apt/sources.list 2>/dev/null; then
    info "apt 源切换到清华镜像"
    cp -n /etc/apt/sources.list "/etc/apt/sources.list.bak.$(date +%s)"
    cat > /etc/apt/sources.list <<EOF
deb ${MIRROR_HOST}/ubuntu/ bionic main restricted universe multiverse
deb ${MIRROR_HOST}/ubuntu/ bionic-updates main restricted universe multiverse
deb ${MIRROR_HOST}/ubuntu/ bionic-backports main restricted universe multiverse
deb ${MIRROR_HOST}/ubuntu/ bionic-security main restricted universe multiverse
EOF
  else
    ok "apt 源已是镜像，跳过"
  fi
fi

info "更新索引并安装基础包"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  build-essential git curl wget ca-certificates \
  vim less htop tmux unzip \
  gdb strace ltrace sysstat \
  pkg-config libc6-dev libpcap-dev \
  linux-tools-generic iproute2 iptables \
  >/dev/null
ok "基础包安装完成"

# 清掉 apt 版 golang，避免与 /usr/local/go 冲突
if dpkg -l 2>/dev/null | grep -qE '^ii\s+(golang|golang-go|golang-1\.)'; then
  warn "检测到 apt 安装的 golang，移除以免干扰"
  apt-get remove -y -qq 'golang*' >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------------------
# 3. Go 工具链
# ---------------------------------------------------------------------------
download_go() {
  local ver="$1" tarball="/tmp/go${1}.linux-amd64.tar.gz"
  if [[ -s "$tarball" ]]; then echo "$tarball"; return 0; fi
  local base
  for base in "https://mirrors.aliyun.com/golang" "https://go.dev/dl"; do
    if curl -fsSL --retry 3 --connect-timeout 20 -o "$tarball" "${base}/go${ver}.linux-amd64.tar.gz"; then
      echo "$tarball"; return 0
    fi
    warn "从 $base 下载 Go $ver 失败，换源重试"
  done
  return 1
}

install_go() {
  local ver="$1" dest="$2"
  if [[ -x "$dest/bin/go" ]]; then ok "Go $ver 已就绪 ($dest)"; return 0; fi
  info "安装 Go $ver → $dest"
  local tarball
  tarball="$(download_go "$ver")" || die "Go $ver 下载失败，请手动下载后重跑"
  rm -rf /tmp/go-x && mkdir -p /tmp/go-x
  tar -C /tmp/go-x -xzf "$tarball"
  rm -rf "$dest"
  mv /tmp/go-x/go "$dest"
  rm -rf /tmp/go-x
  ok "Go $ver 安装完成"
}

install_go "$GO_OLD" "$GO_DIR_OLD"
install_go "$GO_NEW" "$GO_DIR_NEW"

# 切换脚本
cat > /etc/profile.d/go-repro.sh <<'EOF'
export GOPATH=/opt/gopath

go110() {
  export GOROOT=/usr/local/go1.10.8
  export PATH=$GOROOT/bin:$GOPATH/bin:/usr/local/bin:/usr/bin:/bin
  export GO111MODULE=off
  echo "GOROOT=$GOROOT (GOPATH 模式)"
}

go127() {
  export GOROOT=/usr/local/go
  export PATH=$GOROOT/bin:$GOPATH/bin:/usr/local/bin:/usr/bin:/bin
  unset GO111MODULE
  echo "GOROOT=$GOROOT (module 模式)"
}

go127 >/dev/null
EOF
chmod 644 /etc/profile.d/go-repro.sh
ok "已写入 /etc/profile.d/go-repro.sh（新终端生效，或用 source 加载）"

mkdir -p "$GOPATH_DIR/bin" "$WORK_DIR"

# ---------------------------------------------------------------------------
# 4. 系统调优
# ---------------------------------------------------------------------------
info "写入内核参数"
cat > /etc/sysctl.d/99-go-repro.conf <<'EOF'
# etcd / cockroachdb 需要大 mmap 区域
vm.max_map_count = 262144
# 并发实验会打开大量 fd 与连接
fs.file-max = 1048576
net.core.somaxconn = 32768
net.ipv4.ip_local_port_range = 10240 65000
# 崩溃时留 core，便于分析
kernel.core_pattern = /opt/gs/cores/core.%e.%p
EOF
mkdir -p /opt/gs/cores
sysctl --system >/dev/null 2>&1 || sysctl -p /etc/sysctl.d/99-go-repro.conf >/dev/null
ok "内核参数已应用"

cat > /etc/security/limits.d/99-go-repro.conf <<'EOF'
*    soft nofile 1048576
*    hard nofile 1048576
*    soft nproc  65535
*    hard nproc  65535
EOF
ok "ulimit 已放宽（重新登录生效）"

# ---------------------------------------------------------------------------
# 5. 时间同步（对超时类 bug 的复现率影响最大）
# ---------------------------------------------------------------------------
info "配置时间同步"
timedatectl set-timezone UTC 2>/dev/null || true
systemctl enable --now systemd-timesyncd >/dev/null 2>&1 || true
if command -v vmware-toolbox-cmd >/dev/null 2>&1; then
  vmware-toolbox-cmd timesync enable >/dev/null 2>&1 && ok "VMware 时间同步已开启" \
    || warn "vmware-toolbox-cmd timesync 开启失败，请手动勾选 VM 设置里的时间同步"
else
  warn "未检测到 open-vm-tools。建议：apt-get install open-vm-tools，否则挂起后时钟会漂移"
fi

# ---------------------------------------------------------------------------
# 6. 关掉自动更新（防止半夜升级内核把环境改坏）
# ---------------------------------------------------------------------------
info "禁用自动更新服务"
for svc in unattended-upgrades apt-daily apt-daily-upgrade apt-daily.timer apt-daily-upgrade.timer; do
  systemctl disable --now "$svc" >/dev/null 2>&1 || true
done
ok "自动更新已关闭"

if [[ $SWAP_OFF -eq 1 ]]; then
  info "关闭 swap（kubelet 硬性要求）"
  swapoff -a
  sed -i '/\sswap\s/s/^/#/' /etc/fstab
  ok "swap 已关闭并写入 fstab"
fi

# ---------------------------------------------------------------------------
# 7. 可选：克隆上游仓库
# ---------------------------------------------------------------------------
clone_repos() {
  info "克隆 6 个上游仓库到 \$GOPATH/src（切点 $SNAP_DATE 之前）"
  export GOPATH="$GOPATH_DIR"
  local -a specs=(
    "boltdb|https://github.com/boltdb/bolt.git|github.com/boltdb/bolt"
    "grpc-go|https://github.com/grpc/grpc-go.git|google.golang.org/grpc"
    "etcd|https://github.com/etcd-io/etcd.git|github.com/coreos/etcd"
    "docker|https://github.com/moby/moby.git|github.com/moby/moby|partial"
    "cockroachdb|https://github.com/cockroachdb/cockroach.git|github.com/cockroachdb/cockroach|partial"
    "kubernetes|https://github.com/kubernetes/kubernetes.git|k8s.io/kubernetes|partial"
  )
  local spec app url rel mode dir
  for spec in "${specs[@]}"; do
    IFS='|' read -r app url rel mode <<< "$spec"
    mode="${mode:-full}"
    dir="$GOPATH/src/$rel"
    if [[ -d "$dir/.git" ]]; then ok "$app 已存在，跳过"; continue; fi
    mkdir -p "$(dirname "$dir")"
    info "克隆 $app ($mode)"
    local -a extra=()
    if [[ "$mode" == "partial" ]]; then extra=(--filter=tree:0 --no-checkout); fi
    if ! git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 \
           clone --quiet "${extra[@]}" "$url" "$dir"; then
      warn "$app 克隆失败，可稍后单独补"
      rm -rf "$dir"
      continue
    fi
    git -C "$dir" config core.longpaths true
    git -C "$dir" config core.autocrlf false
    local sha
    # --first-parent 必须加，否则会挑到侧分支 commit（祖先链很短）
    sha="$(git -C "$dir" rev-list -1 --first-parent --before="$SNAP_DATE" HEAD 2>/dev/null || true)"
    if [[ -n "$sha" ]]; then
      git -C "$dir" checkout --quiet "$sha" 2>/dev/null || warn "$app checkout 失败（可能缺文件，先不管）"
      ok "$app → ${sha:0:12} ($(git -C "$dir" log -1 --format=%ad --date=short "$sha" 2>/dev/null)) commits=$(git -C "$dir" rev-list --count "$sha" 2>/dev/null || echo '?')"
    fi
  done
}

if [[ $WITH_REPOS -eq 1 ]]; then clone_repos; fi

# ---------------------------------------------------------------------------
# 8. 验收报告
# ---------------------------------------------------------------------------
info "生成验收报告 → $REPORT"
{
  echo "# Linux 环境验收报告"
  echo
  echo "生成时间: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "| 检查项 | 实际值 | 期望 | 结论 |"
  echo "|---|---|---|---|"
  chk() {
    local name="$1" val="$2" want="$3"
    local flag="✅"
    if [[ "${4:-}" == "soft" ]]; then flag="ℹ️"; fi
    echo "| $name | \`$val\` | $want | $flag |"
  }
  chk "发行版" "$(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY | cut -d= -f2)" "Ubuntu 18.04"
  chk "内核" "$(uname -r)" "4.15.x（soft）" soft
  chk "cgroup 版本" "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)" "tmpfs = v1"
  chk "iptables" "$(iptables --version 2>/dev/null | head -1)" "(legacy)"
  chk "gcc" "$(gcc -dumpversion 2>/dev/null)" ">= 5"
  chk "CPU 核数" "$(nproc)" "4（固定）"
  chk "内存" "$(free -g | awk '/^Mem:/{print $2}') GB" "8 GB"
  echo
  echo "## Go 工具链"
  echo
  echo '```'
  for d in "$GO_DIR_OLD" "$GO_DIR_NEW"; do
    if [[ -x "$d/bin/go" ]]; then echo "$d → $("$d/bin/go" version)"; fi
  done
  echo '```'
  echo
  echo "## 切换方式"
  echo
  echo '```bash'
  echo 'go110   # Go 1.10.8，GOPATH 模式（编 2018 年快照代码）'
  echo 'go127   # Go 1.27.3，module 模式（编 goast、做现代对照）'
  echo '```'
  echo
  echo "## 关键参数"
  echo
  echo '```'
  echo "vm.max_map_count = $(sysctl -n vm.max_map_count 2>/dev/null)"
  echo "fs.file-max      = $(sysctl -n fs.file-max 2>/dev/null)"
  echo "ulimit -n (当前) = $(ulimit -n)"
  echo "swap             = $(free -h | awk '/^Swap:/{print $2}')"
  echo "时区             = $(timedatectl show -p Timezone --value 2>/dev/null)"
  echo '```'
  echo
  echo "## 复现链路自检"
  echo
  echo '跑完下面两条，能通过就说明 P4 的地基是通的：'
  echo
  echo '```bash'
  echo 'source /etc/profile.d/go-repro.sh && go110'
  echo 'cd $GOPATH/src/github.com/boltdb/bolt && go test ./...'
  echo 'CGO_ENABLED=1 go test -race ./...    # -race 需要 gcc，验证 P5 可行'
  echo '```'
} > "$REPORT"
ok "报告已写入 $REPORT"

echo
echo "============================================================"
ok "环境准备完成。请 exit 后重新登录（或 source /etc/profile.d/go-repro.sh）"
echo "  下一步："
echo "    go110 && cd \$GOPATH/src/github.com/boltdb/bolt && go test ./..."
echo "  并立刻在 VMware 里打快照 01-base-ready"
echo "============================================================"
