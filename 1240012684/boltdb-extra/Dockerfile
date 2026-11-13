# Pinned build environment for the CS340 BoltDB#392 replication.
# Build:  docker build -t boltdb392-repro .
# Run:    docker run --rm boltdb392-repro make verify
#
# The authoritative toolchain used for every number in report/report.pdf is
# recorded in results/environment.txt (Go 1.26.8, Ubuntu 26.04, kernel
# 6.18.33.2-microsoft-standard-WSL2).  This image pins the same Go minor
# release so a clean machine can rebuild without relying on a host Go install.
FROM golang:1.26-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash coreutils gcc git python3 make curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . .
ENV GOPROXY=off GOSUMDB=off GOTRACEBACK=all

RUN chmod +x scripts/*.sh setup.sh \
 && make build \
 && make verify

CMD ["make", "run"]
