GO      ?= go
REPEAT  ?= 20
TIMEOUT ?= 5s
BIN     := bin/repro

.PHONY: all build verify run analyze clean

all: build

build:
	@mkdir -p bin
	GOPROXY=off GOSUMDB=off $(GO) build -o $(BIN) ./cmd/repro

verify: build
	@set -e; \
	for bug in double-rlock miss-unlock; do \
	  for mode in buggy fixed; do \
	    log=$$(mktemp); \
	    set +e; timeout 5s $(BIN) -bug=$$bug -mode=$$mode -run-id=verify > $$log 2>&1; rc=$$?; set -e; \
	    if [ "$$mode" = buggy ]; then \
	      [ "$$rc" -eq 2 ] && grep -q "all goroutines are asleep" $$log || { echo "FAIL $$bug/$$mode"; cat $$log; rm -f $$log; exit 1; }; \
	    else \
	      [ "$$rc" -eq 0 ] && grep -q "status=finished" $$log || { echo "FAIL $$bug/$$mode"; cat $$log; rm -f $$log; exit 1; }; \
	    fi; \
	    echo "PASS $$bug/$$mode (rc=$$rc)"; rm -f $$log; \
	  done; \
	done

run: build
	@REPEAT=$(REPEAT) TIMEOUT_SEC=$(TIMEOUT) bash scripts/run_experiments.sh

analyze:
	@python3 scripts/analyze.py

clean:
	rm -rf bin results/raw/* results/summary.csv results/statistics.csv \
	       results/table_results.md results/figK1_detection_rate.svg
