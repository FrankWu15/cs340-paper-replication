#!/usr/bin/env bash
# Build and run both sides, capture raw output under logs/.
# Usage: ./run.sh            (uses go from PATH, or $GO)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
GO="${GO:-go}"
mkdir -p logs

{
  echo "date: $(date -Is 2>/dev/null || date)"
  echo "go:   $($GO version)"
  echo "os:   $(uname -srm)"
} > logs/environment.txt

bin_name() {
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) echo "logs/.bin-$1.exe" ;;
    *) echo "logs/.bin-$1" ;;
  esac
}

run_side() {
  side="$1"
  bin="$(bin_name "$side")"
  if ! $GO build -o "$bin" "./$side/main.go" > "logs/${side}.build.log" 2>&1; then
    echo "BUILD_FAIL" > "logs/${side}.log"
    cat "logs/${side}.build.log" >> "logs/${side}.log"
    return 1
  fi
  if command -v timeout >/dev/null 2>&1; then
    timeout 120 "$bin" > "logs/${side}.log" 2>&1
  else
    "$bin" > "logs/${side}.log" 2>&1
  fi
  echo "exit=$?" >> "logs/${side}.log"
}

run_side buggy
run_side fixed

verdict() {
  f="logs/$1.log"
  if grep -q "all goroutines are asleep - deadlock" "$f" 2>/dev/null; then
    echo "DEADLOCK"
  elif grep -q "^exit=0$" "$f" 2>/dev/null; then
    echo "CLEAN"
  else
    echo "OTHER"
  fi
}

b="$(verdict buggy)"
f="$(verdict fixed)"
printf 'buggy=%s fixed=%s\n' "$b" "$f" | tee logs/verdict.txt
[ "$b" = "DEADLOCK" ] && [ "$f" = "CLEAN" ]
