GO        ?= go
REPEAT    ?= 20
TIMEOUT   ?= 8s
BIN       := bin/repro

.PHONY: build verify run analyze clean

build:
	@$(GO) build -o $(BIN) ./cmd/repro

verify:
	@bash scripts/verify.sh

run:
	@REPEAT=$(REPEAT) TIMEOUT_SEC=$(TIMEOUT) bash scripts/run_experiments.sh

analyze:
	@python3 scripts/analyze.py

clean:
	@rm -rf bin results/raw results/summary.csv results/statistics.csv results/figures
	@echo "cleaned build & result artifacts (nothing under version control removed)"
