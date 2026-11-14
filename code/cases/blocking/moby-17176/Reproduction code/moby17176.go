package main

import (
    "fmt"
    "sync"
    "time"
)

type DeviceSet struct {
    sync.Mutex
    nrDeletedDevices int
}

// simulating the original code with bugs
func (devices *DeviceSet) cleanupDeletedDevicesBuggy() {
    devices.Lock()

    if devices.nrDeletedDevices == 0 {
        return // mutex not released
    }

    devices.Unlock()
}

// simulating the fixed code
func (devices *DeviceSet) cleanupDeletedDevicesFixed() {
    devices.Lock()

    if devices.nrDeletedDevices == 0 {
        devices.Unlock()
        return
    }

    devices.Unlock()
}

func checkLock(name string, devices *DeviceSet) {
    done := make(chan bool, 1)

    go func() {
        devices.Lock()
        defer devices.Unlock()
        done <- true
    }()

    select {
    case <-done:
        fmt.Println(name, ": 成功获取锁")
    case <-time.After(2 * time.Second):
        fmt.Println(name, ": 获取锁超时，发生死锁")
    }
}

func main() {
    fmt.Println("===== Docker moby#17176 最小复现 =====")

    buggy := &DeviceSet{nrDeletedDevices: 0}
    buggy.cleanupDeletedDevicesBuggy()
    checkLock("原始代码", buggy)

    fixed := &DeviceSet{nrDeletedDevices: 0}
    fixed.cleanupDeletedDevicesFixed()
    checkLock("修复代码", fixed)
}
