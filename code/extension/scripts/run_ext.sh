#!/usr/bin/env bash
# Extension experiment driver (repo layout).
#
# Sweeps GOMAXPROCS over existing cases under code/cases/ — it does NOT carry
# its own copy of the bug sources (repo rule: a case exists once, under
# code/cases/<class>/<id>/).
#
# Two dimensions measured:
#   plain : trigger rate + trigger intensity (violations per run)
#   -race : whether `WARNING: DATA RACE` appears (race-detector hit rate)
#
# Usage:
#   bash scripts/run_ext.sh                # full run (~20 min on 12 cores)
#   LEVELS="1 12" N_PROB=3 N_DET=2 N_RACE=3 bash scripts/run_ext.sh   # smoke test
#
# Output: results/raw_runs.csv (one row per run)
set -u
EXT="$(cd "$(dirname "$0")/.." && pwd)"          # code/extension
CODE="$(cd "$EXT/.." && pwd)"                     # code
CASES="$CODE/cases"

export GO111MODULE=off
W="${WORK:-/tmp/ext_bin}"; mkdir -p "$W"
RAW="$EXT/results/raw_runs.csv"

LEVELS="${LEVELS:-1 2 4 8 12}"
N_PROB="${N_PROB:-30}"   # probabilistic cases (cockroachdb-17112, moby-28682)
N_DET="${N_DET:-12}"     # deterministic cases (kubernetes-36377, moby-8909, kubernetes-30872)
N_RACE="${N_RACE:-30}"

# case -> class + source dir
case_dir() {
  case "$1" in
    cockroachdb-17112|moby-28682|kubernetes-36377) echo "$CASES/non-blocking/$1" ;;
    *)                                             echo "$CASES/blocking/$1" ;;
  esac
}
PROB_CASES="cockroachdb-17112 moby-28682"
DET_CASES="kubernetes-36377 moby-8909 kubernetes-30872"
RACE_CASES="cockroachdb-17112 kubernetes-36377 moby-28682"

echo "=== build (plain + fixed) ==="
for c in $PROB_CASES $DET_CASES; do
  d=$(case_dir "$c")
  go build -o "$W/$c"       "$d/buggy/main.go" || { echo "BUILD FAIL $c"; exit 1; }
  go build -o "$W/${c}_fixed" "$d/fixed/main.go" || { echo "BUILD FAIL fixed $c"; exit 1; }
  echo "  ok $c"
done
echo "=== build (-race) ==="
for c in $RACE_CASES; do
  d=$(case_dir "$c")
  go build -race -o "$W/${c}_race" "$d/buggy/main.go" || { echo "RACE BUILD FAIL $c"; exit 1; }
  echo "  ok $c (race)"
done

echo "case,class,gp,phase,run,verdict,trig,metric,race_flag,rc" > "$RAW"

# run_one <binary> <gp> <timeout>  -> "rc|verdict|metric|race_flag"
run_one() {
  local bin="$1" gp="$2" to="$3" out rc verd metric raced
  out=$(env GOMAXPROCS="$gp" timeout "$to" "$bin" 2>&1); rc=$?
  verd=$(printf '%s' "$out" | grep -o 'VERDICT: [A-Z]*' | head -1 | sed 's/VERDICT: //')
  metric=$(printf '%s' "$out" | grep -oE '不一致 [0-9]+ 次|missed_close_stdin=[0-9]+' | head -1 | grep -oE '[0-9]+' | head -1)
  [ -z "$metric" ] && metric=0
  raced=0; printf '%s' "$out" | grep -q 'WARNING: DATA RACE' && raced=1
  echo "$rc|$verd|$metric|$raced"
}

echo "=== D1: trigger rate (plain) ==="
for c in $PROB_CASES $DET_CASES; do
  cls=non-blocking; case "$c" in moby-8909|kubernetes-30872) cls=blocking;; esac
  if echo " $PROB_CASES " | grep -q " $c "; then N=$N_PROB; else N=$N_DET; fi
  for gp in $LEVELS; do
    for i in $(seq 1 $N); do
      IFS='|' read rc verd metric raced <<< "$(run_one "$W/$c" "$gp" 15)"
      trig=0; { [ "$verd" = "BUG" ] || [ "$verd" = "DEADLOCK" ]; } && trig=1
      echo "$c,$cls,$gp,plain,$i,$verd,$trig,$metric,0,$rc" >> "$RAW"
    done
    echo "  $c gp=$gp done ($N)"
  done
done

echo "=== fixed control (expect 0 triggers) ==="
for c in $PROB_CASES $DET_CASES; do
  cls=non-blocking; case "$c" in moby-8909|kubernetes-30872) cls=blocking;; esac
  for gp in 1 12; do
    for i in $(seq 1 5); do
      IFS='|' read rc verd metric raced <<< "$(run_one "$W/${c}_fixed" "$gp" 15)"
      trig=0; { [ "$verd" = "BUG" ] || [ "$verd" = "DEADLOCK" ]; } && trig=1
      echo "$c,$cls,$gp,fixed,$i,$verd,$trig,$metric,0,$rc" >> "$RAW"
    done
  done
done
echo "  fixed control done"

echo "=== D2: race-detector hit rate (-race) ==="
for c in $RACE_CASES; do
  for gp in $LEVELS; do
    for i in $(seq 1 $N_RACE); do
      IFS='|' read rc verd metric raced <<< "$(run_one "$W/${c}_race" "$gp" 60)"
      trig=0; [ "$verd" = "BUG" ] && trig=1
      echo "$c,non-blocking,$gp,race,$i,$verd,$trig,$metric,$raced,$rc" >> "$RAW"
    done
    echo "  $c gp=$gp race done ($N_RACE)"
  done
done

echo "DONE — rows: $(wc -l < "$RAW")"
echo "next: python3 scripts/analyze.py"
