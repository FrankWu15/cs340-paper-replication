Reproduction of Docker Concurrency Bug moby#17176

1. Project Overview

This project reproduces and analyzes a blocking concurrency bug in Docker (Moby), identified as moby#17176 in the Go concurrency bug dataset.

The root cause of this bug is a missing mutex unlock operation in the cleanupDeletedDevices() function. Under a specific condition, the function returns without releasing a previously acquired mutex. As a result, other Goroutines attempting to acquire the same mutex become blocked.

This experiment includes:

Analysis of the original bug.

A minimal Go program simulating the buggy and fixed behavior.

Source code comparison between the buggy and fixed versions.

Compilation and execution of the official Docker regression test.

2. Bug Information

Item                         Description

Project                      Moby / Docker

Issue                        moby#17176

Bug Category                 Blocking Bug

Fix Commit                   2f16895ee94848e2d8ad72bc01968b4c88d84cb8

Parent Commit (Before Fix)   8eba018b610e425960ffb4620dd7a0bfde5238d9

Author                       Vivek Goyal

Date                         October 19, 2015

Affected File                daemon/graphdriver/devmapper/deviceset.go

Affected Function            cleanupDeletedDevices()

Official fix commit:

https://github.com/moby/moby/commit/2f16895ee94848e2d8ad72bc01968b4c88d84cb8

3. Bug Description and Root Cause

In the buggy version, the function acquires a mutex and returns directly when there are no deleted devices:

devices.Lock()

if devices.nrDeletedDevices == 0 {
    return nil
}

The mutex is not automatically released when the function returns. Since devices.Unlock() is missing, the mutex remains locked.

Consequently, other Goroutines attempting to acquire the same mutex cannot proceed, resulting in blocking.

Official Fix

The official patch adds an unlock operation before returning:

devices.Lock()

if devices.nrDeletedDevices == 0 {
    devices.Unlock()
    return nil
}

This ensures that the mutex is properly released before the function exits.

4. Experimental Environment

Operating System: Ubuntu 22.04 LTS

Virtualization: VMware Workstation

Architecture: x86_64

Go Version: Go 1.18.1 linux/amd64

Git Version: 2.34.1

Build Mode: GOPATH mode

Build Settings: GO111MODULE=off, -tags daemon

5. Experimental Procedure and Results

5.1 Minimal Reproduction

A minimal Go program, moby17176.go, was developed using Go's standard library sync.Mutex to simulate the mutex behavior in Docker.

Two implementations were tested:

Buggy version: Acquires the mutex but does not release it before returning.

Fixed version: Releases the mutex before returning.

Another Goroutine then attempts to acquire the same mutex. A timeout mechanism is used to detect blocking.

Run the program:

go run moby17176.go

Actual output:

===== Docker moby#17176 Minimal Reproduction =====
Original code : Timed out acquiring the lock (deadlock)
Fixed code    : Successfully acquired the lock

The result demonstrates that the missing unlock operation causes subsequent Goroutines to become blocked, while the fixed implementation allows the mutex to be acquired successfully.

Note: This is a mechanism-level minimal reproduction, not a full execution of the Docker service.

5.2 Source Code Comparison

The original and fixed versions of:

daemon/graphdriver/devmapper/deviceset.go

were examined and compared.

The key change in the official patch is the addition of:

devices.Unlock()

before the early return.

The source code difference is saved in deviceset.diff.

5.3 Official Docker Regression Test

The devicemapper test binary was compiled using the fixed Docker source code:

GO111MODULE=off go test -tags daemon -c ./daemon/graphdriver/devmapper

The target test was verified:

./devmapper.test -test.list '^TestDevmapperLockReleasedDeviceDeletion$'

The official regression test was then executed:

sudo ./devmapper.test \
-test.run '^TestDevmapperLockReleasedDeviceDeletion$' \
-test.v

Actual test output:

=== RUN   TestDevmapperLockReleasedDeviceDeletion
--- PASS: TestDevmapperLockReleasedDeviceDeletion (0.93s)
PASS

Result: The official Docker regression test passed on the fixed source version, completing in approximately 0.93 seconds.

Note: The official regression test was executed on the fixed version. The official test was not executed against the original buggy Docker source in this experiment.

6. Directory Structure

Docker_moby17176_Experiment/
│
├── README.md
│
│
├── Reproduction_Code/
│   └── moby17176.go
│
├── Screenshots/
│   ├── 01_Minimal_Reproduction.png
│   ├── 02_Source_Code_Comparison.png
│   └── 03_Official_Test_PASS.png
│
└── Source_Comparison/
    ├── deviceset_before.go
    ├── deviceset_after.go
    ├── deviceset.diff
    └── devmapper_test.go

7. Conclusion

This experiment analyzed and reproduced Docker concurrency bug moby#17176, which was caused by a missing mutex unlock operation.

The minimal Go program demonstrated how failing to release a mutex can block other Goroutines. Source code comparison identified the exact change introduced by the official fix. Finally, the official Docker regression test was successfully compiled and executed on the fixed source version.

The experiment highlights the importance of proper mutex management in concurrent Go programs. In particular, developers should ensure that locks are released on every execution path, including conditional branches and early returns, to prevent Goroutine blocking.