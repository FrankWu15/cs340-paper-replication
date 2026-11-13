#!/usr/bin/env bash
# One-shot environment check and (optional) source re-fetch.
#
# The pinned BoltDB source is already vendored under third_party/bolt, so a
# clean machine needs only Go >= 1.20, bash, coreutils and python3.  This
# script verifies that and can re-fetch the exact upstream commit if the
# vendored copy is missing.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BOLT_COMMIT="2f1ce7a837dcb8da3ec595b1dac9d0632f0f99e8"
BOLT_TARBALL_SHA256="95dc5842dab55f7519b7002bbec648321277b5d6f0ad59aab509ee59313b6386"
BOLT_URL="https://github.com/boltdb/bolt/archive/${BOLT_COMMIT}.tar.gz"

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING: $1" >&2; exit 1; }; }
for tool in go python3 gcc git timeout date sha256sum curl tar; do need "$tool"; done

GO_MAJOR=$(go version | awk '{print $3}' | sed 's/^go//' | cut -d. -f1)
GO_MINOR=$(go version | awk '{print $3}' | sed 's/^go//' | cut -d. -f2)
if [ "$GO_MAJOR" -lt 1 ] || { [ "$GO_MAJOR" -eq 1 ] && [ "$GO_MINOR" -lt 20 ]; }; then
  echo "Go >= 1.20 is required, found $(go version)" >&2
  exit 1
fi

if [ ! -f third_party/bolt/db.go ]; then
  echo "[setup] vendored BoltDB missing; fetching pinned commit $BOLT_COMMIT"
  tarball="$(mktemp)"
  trap 'rm -f "$tarball"' EXIT
  curl -fsSL "$BOLT_URL" -o "$tarball"
  actual=$(sha256sum "$tarball" | awk '{print $1}')
  if [ "$actual" != "$BOLT_TARBALL_SHA256" ]; then
    echo "SHA256 mismatch: expected $BOLT_TARBALL_SHA256, got $actual" >&2
    exit 1
  fi
  mkdir -p third_party/bolt
  tar -xzf "$tarball" --strip-components=1 -C third_party/bolt \
      --wildcards "*/LICENSE" "*/*.go"
  find third_party/bolt -name "*_test.go" -delete
  printf "module github.com/boltdb/bolt\n\ngo 1.20\n" > third_party/bolt/go.mod
  echo "$BOLT_COMMIT" > third_party/bolt/UPSTREAM_COMMIT.txt
fi

echo "[setup] OK: $(go version), $(python3 --version 2>&1), $(gcc --version | head -1)"
echo "[setup] BoltDB: $(cat third_party/bolt/UPSTREAM_COMMIT.txt)"
echo "[setup] next: make build && make verify && make run && make report"
