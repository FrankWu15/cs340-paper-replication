# CS340 Research Paper Replication - BoltDB#392
# All paths are relative to this Makefile; no absolute paths are hard-coded.

GO        ?= go
PYTHON    ?= python3
REPEAT    ?= 10
TIMEOUT   ?= 5s
BIN       := bin/repro

.PHONY: all build run analyze report clean verify help

all: build

build:
	@mkdir -p bin
	GOPROXY=off GOSUMDB=off $(GO) build -o $(BIN) ./cmd/repro

# One deterministic smoke test of every mode (buggy must print a deadlock).
verify: build
	@bash scripts/verify.sh

# Full experiment: REPEAT trials per mode, raw logs + CSV + statistics + figures.
run: build
	@REPEAT=$(REPEAT) TIMEOUT_SEC=$(TIMEOUT) bash scripts/run_experiments.sh

analyze:
	@$(PYTHON) scripts/analyze.py

# Requires reportlab + svglib: pip install reportlab svglib
# Override the interpreter on hosts without a system-wide python3, e.g.
#   make report PYTHON=/path/to/venv/bin/python
report:
	@$(PYTHON) scripts/make_report.py

clean:
	rm -rf bin results/raw/* results/summary.csv results/statistics.csv \
	       results/table_paper_vs_ours.md results/table_results.md \
	       results/figures/*.svg report/report.pdf

help:
	@echo "Targets:"
	@echo "  make build    - build the repro binary (offline, vendored BoltDB)"
	@echo "  make verify   - one smoke trial per mode"
	@echo "  make run      - REPEAT=$(REPEAT) trials per mode, saves raw logs + CSV"
	@echo "  make analyze  - recompute mean +/- std and the SVG figures"
	@echo "  make report   - build report/report.pdf (needs reportlab + svglib)"
	@echo "  make clean    - remove generated binaries, logs and report"
