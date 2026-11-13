#!/usr/bin/env bash
# build_and_run_realcompile.sh
# Compile and RUN the REAL upstream etcd code for the double-lock bug
# (httpClusterClient.Sync self-deadlock, buggy commit 83930ac1) and let Go's
# built-in deadlock detector confirm the bug.
#
# The extracted client.go / members.go are VERBATIM from upstream 83930ac1
# except for three toolchain adaptations required to build 2016 code on a
# modern Go toolchain (none of which touch the bug logic):
#   1. context import: golang.org/x/net/context  ->  standard "context"
#   2. http.Transport.Dial        -> DialContext (field renamed in modern Go)
#   3. github.com/coreos/etcd/pkg/types -> local stub "realetcd/client/types"
#      (pkg/types is only used by the unrelated Add() method, not by Sync/List/Do)
set -u

ETCD_SRC="${ETCD_SRC:-$HOME/etcd-src}"
ROOT=/mnt/c/Users/30683/WorkBuddy/2026-11-05-11-07-12/etcd-bugs-repro
RC="$ROOT/realcompile"
LOG="$ROOT/results/real-source-evidence/realcompile_run.log"
mkdir -p "$RC/client/types"

# --- extract REAL upstream source, adapt only the toolchain bits ---
git -C "$ETCD_SRC" show 83930ac1:client/client.go \
  | sed -e 's#"github.com/coreos/etcd/Godeps/_workspace/src/golang.org/x/net/context"#"context"#' \
         -e 's#Dial: (&net.Dialer{#DialContext: (\&net.Dialer{#' \
         -e 's#}).Dial,#}).DialContext,#' \
  > "$RC/client/client.go"

git -C "$ETCD_SRC" show 83930ac1:client/members.go \
  | sed -e 's#"github.com/coreos/etcd/Godeps/_workspace/src/golang.org/x/net/context"#"context"#' \
         -e 's#"github.com/coreos/etcd/pkg/types"#"realetcd/client/types"#' \
  > "$RC/client/members.go"

cat > "$RC/go.mod" <<'EOF'
module realetcd

go 1.20
EOF

# minimal stub for the unrelated pkg/types (used only by Add(), not by Sync)
cat > "$RC/client/types/types.go" <<'EOF'
package types

import "net/url"

// URLs is a list of URL instances.
type URLs []url.URL

// NewURLs parses a slice of strings into URLs.
func NewURLs(us []string) (URLs, error) {
	urls := make(URLs, len(us))
	for i := range us {
		u, err := url.Parse(us[i])
		if err != nil {
			return nil, err
		}
		urls[i] = *u
	}
	return urls, nil
}
EOF

# driver: calls the REAL httpClusterClient.Sync from upstream 83930ac1
#
# A watchdog confirms the self-deadlock. Because the real client package
# imports net/http, a runtime netpoller goroutine stays alive, so Go's native
# "all goroutines are asleep" detector never fires (it only fires when *every*
# goroutine is blocked). We instead run the REAL Sync() in a goroutine and
# assert it never returns within 5s -- that hang is exactly the upstream bug.
cat > "$RC/main.go" <<'EOF'
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"realetcd/client"
)

func main() {
	cfg := client.Config{
		Endpoints: []string{"http://127.0.0.1:1"},
	}
	c, err := client.New(cfg)
	if err != nil {
		panic(err)
	}
	fmt.Println("calling REAL httpClusterClient.Sync() from buggy commit 83930ac1 ...")

	ctx := context.Background()
	done := make(chan struct{})
	go func() {
		// Real upstream bug: Sync() holds c.Lock() then calls
		// List() -> c.Do() -> c.RLock() on the SAME RWMutex (self-deadlock).
		_ = c.Sync(ctx)
		close(done)
	}()

	select {
	case <-done:
		fmt.Println("returned (this line should never print)")
	case <-time.After(5 * time.Second):
		fmt.Println("CONFIRMED: real upstream httpClusterClient.Sync self-deadlock")
		fmt.Println("(blocked in RLock while holding Lock; Go's native deadlock")
		fmt.Println(" detector does not fire because net/http keeps a netpoller")
		fmt.Println(" goroutine alive, so the scheduler never sees all-asleep)")
		os.Exit(2)
	}
}
EOF

cd "$RC"
{
  echo "=== go build ./... (real upstream etcd client code) ==="
  go build ./... 2>&1
  echo "build rc=$?"
  echo
  echo "=== go run . (expect: fatal error: all goroutines are asleep - deadlock!, exit 2) ==="
  go run . ; rc=$?
  echo
  echo "PROGRAM_EXIT_CODE=$rc"
} 2>&1 | tee "$LOG"
