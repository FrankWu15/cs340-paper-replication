// 探针：从真实 DialContext 路径观测 grpc#1424 的协程残留（个人实验，2026-11-19）
//
// 官方回归测试 TestClientLBWatcherWithClosedBalancer 直接调用 cc.lbWatcher(doneChan)，
// 只验证「Notify 先关闭时 doneChan 是否被关闭」这一通知契约。本探针不碰内部函数：
// 它只用公开 API 建立真实的 DialContext 调用，进入 balancer 分支后取消 context，
// 再用 runtime.Stack 在进程内定位仍然停在 clientconn.go:409 `<-doneChan` 的匿名协程。
//
// 同一份文件原样复制到 buggy(39c8c386) 与 fixed(4e56696c) 两棵源码树，产品代码不改。
//
// 环境变量：
//   XU_SIDE       buggy | fixed（仅用于标注）
//   XU_MODE       cancel | deadline | noblock
//   XU_N          本进程内顺序调用 DialContext 的次数
//   XU_ROUND      轮次编号（仅用于标注）
//   XU_OUT        输出目录，写 metrics.json 与 goroutine dump
//   XU_WINDOW_MS  每次调用返回后的观察窗口，默认 200
//   XU_HARD_MS    单次调用的硬超时，默认 5000
//   XU_DEADLINE_MS  deadline 模式的 context 超时，默认 1500
package grpc_test

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/net/context"
	"google.golang.org/grpc"
)

// targetLine 是两棵源码树里 <-doneChan 所在行；buggy 与 fixed 在该行之前完全相同，
// 修复只改了 lbWatcher（613 行之后），因此两侧都是 clientconn.go:409。
const targetLine = "clientconn.go:409"

// ---------------------------------------------------------------- balancer

// xuBal 是不发布任何地址的 balancer：Notify 返回非 nil 通道，Close 幂等地关闭它。
// 关闭完全由连接生命周期驱动（DialContext 的 defer -> cc.Close -> balancer.Close），
// 探针不直接改库内部状态。
type xuBal struct {
	ch       chan []grpc.Address
	notifyN  int32
	ready    chan struct{}
	readyOne sync.Once
	closeOne sync.Once
	mu       sync.Mutex
	events   []string
	t0       time.Time
}

func newXuBal(t0 time.Time) *xuBal {
	return &xuBal{ch: make(chan []grpc.Address), ready: make(chan struct{}), t0: t0}
}

func (b *xuBal) ev(format string, a ...interface{}) {
	b.mu.Lock()
	b.events = append(b.events, fmt.Sprintf("%9.3fms  %s",
		float64(time.Since(b.t0).Microseconds())/1000.0, fmt.Sprintf(format, a...)))
	b.mu.Unlock()
}

func (b *xuBal) Start(target string, cfg grpc.BalancerConfig) error {
	b.ev("balancer.Start(%q)", target)
	return nil
}

func (b *xuBal) Up(addr grpc.Address) func(error) {
	b.ev("balancer.Up(%q)", addr.Addr)
	return func(err error) { b.ev("balancer.down(%v)", err) }
}

func (b *xuBal) Get(ctx context.Context, opts grpc.BalancerGetOptions) (grpc.Address, func(), error) {
	b.ev("balancer.Get(blockingWait=%v)", opts.BlockingWait)
	return grpc.Address{}, nil, errors.New("xu: no address published")
}

func (b *xuBal) Notify() <-chan []grpc.Address {
	n := atomic.AddInt32(&b.notifyN, 1)
	b.ev("balancer.Notify #%d", n)
	// 第 1 次来自 DialContext 自身，第 2 次来自 lbWatcher 的 for range：
	// 第 2 次发生即说明 lbWatcher 已经进入循环。
	if n == 2 {
		b.readyOne.Do(func() { close(b.ready) })
	}
	return b.ch
}

func (b *xuBal) Close() error {
	b.closeOne.Do(func() {
		b.ev("balancer.Close -> close(Notify)")
		close(b.ch)
	})
	return nil
}

func (b *xuBal) eventsSnapshot() []string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return append([]string(nil), b.events...)
}

// ---------------------------------------------------------------- 栈分析

type counts struct {
	total     int
	target    int
	lbWatcher int
}

// analyze 按空行切分 goroutine 块，只统计以 "goroutine " 开头的块，
// 因此 "created by ..." 行不会把创建者误算成一个协程。
func analyze(s string) counts {
	var c counts
	for _, blk := range strings.Split(s, "\n\n") {
		b := strings.TrimSpace(blk)
		if !strings.HasPrefix(b, "goroutine ") || !strings.Contains(b, "[") {
			continue
		}
		c.total++
		// 不预设编译器的闭包编号：只要求是 DialContext 内的匿名函数，且栈帧落在
		// clientconn.go:409（两侧源码该行都是 <-doneChan）。
		if strings.Contains(b, "google.golang.org/grpc.DialContext.func") && strings.Contains(b, targetLine) {
			c.target++
		}
		if strings.Contains(b, "(*ClientConn).lbWatcher") {
			c.lbWatcher++
		}
	}
	return c
}

func stackAll() string {
	for size := 1 << 20; ; size *= 2 {
		buf := make([]byte, size)
		n := runtime.Stack(buf, true)
		if n < size || size >= 1<<26 {
			return string(buf[:n])
		}
	}
}

func snapshot() counts { return analyze(stackAll()) }

func writeDump(t *testing.T, path string) {
	if err := os.WriteFile(path, []byte(stackAll()), 0o644); err != nil {
		t.Logf("写 dump 失败 %s: %v", path, err)
	}
}

// waitTarget 轮询直到目标栈数量达到 want 或超时，返回最后观察到的数量。
// 它只读状态，不改变被测程序的行为。
func waitTarget(want int, timeout time.Duration) int {
	deadline := time.Now().Add(timeout)
	last := -1
	for {
		c := snapshot()
		last = c.target
		if last == want || time.Now().After(deadline) {
			return last
		}
		time.Sleep(2 * time.Millisecond)
	}
}

// ---------------------------------------------------------------- 结果结构

type xuCall struct {
	Iter          int      `json:"iter"`
	Trigger       string   `json:"trigger"`
	TargetSeenMS  float64  `json:"target_seen_ms"`
	CancelMS      float64  `json:"cancel_ms"`
	ReturnMS      float64  `json:"return_ms"`
	ElapsedMS     float64  `json:"return_elapsed_ms"`
	Returned      bool     `json:"dial_returned"`
	ReturnedNilCC bool     `json:"returned_nil_conn"`
	Err           string   `json:"dial_error"`
	TargetBefore  int      `json:"target_stacks_before"`
	TargetSamples []int    `json:"target_stacks_samples"`
	TargetAfter   int      `json:"target_stacks_after"`
	LbWatcherAfter int     `json:"lbwatcher_stacks_after"`
	GoroutinesAfter int    `json:"goroutines_after"`
	Notes         []string `json:"notes,omitempty"`
}

type xuMetrics struct {
	Version         string   `json:"version"`
	Mode            string   `json:"context_mode"`
	N               int      `json:"n"`
	Round           int      `json:"round"`
	WindowMS        int      `json:"observation_window_ms"`
	HardMS          int      `json:"hard_timeout_ms"`
	DeadlineMS      int      `json:"deadline_ms"`
	ReturnedCalls   int      `json:"returned_calls"`
	ContextErrors   int      `json:"context_errors"`
	DialErrors      []string `json:"dial_errors"`
	TargetBefore    int      `json:"target_stacks_before"`
	TargetAfter     int      `json:"target_stacks_after"`
	LbWatcherBefore int      `json:"lbwatcher_stacks_before"`
	LbWatcherAfter  int      `json:"lbwatcher_stacks_after"`
	GoroutinesBefore int     `json:"goroutines_before"`
	GoroutinesAfter int      `json:"goroutines_after"`
	PerCall         []xuCall `json:"per_call"`
	Events          []string `json:"events"`
	Notes           []string `json:"notes,omitempty"`
	StartedAt       string   `json:"started_at"`
	FinishedAt      string   `json:"finished_at"`
}

// ---------------------------------------------------------------- 主流程

func TestXuDialContextLeak(t *testing.T) {
	side := envStr("XU_SIDE", "unknown")
	mode := envStr("XU_MODE", "cancel")
	n := envInt("XU_N", 1)
	round := envInt("XU_ROUND", 1)
	winMS := envInt("XU_WINDOW_MS", 200)
	hardMS := envInt("XU_HARD_MS", 5000)
	ddlMS := envInt("XU_DEADLINE_MS", 1500)

	out := os.Getenv("XU_OUT")
	if out == "" {
		out = t.TempDir()
	}
	if err := os.MkdirAll(out, 0o755); err != nil {
		t.Fatalf("创建输出目录失败: %v", err)
	}
	win := time.Duration(winMS) * time.Millisecond
	hard := time.Duration(hardMS) * time.Millisecond
	ddl := time.Duration(ddlMS) * time.Millisecond

	m := &xuMetrics{
		Version: side, Mode: mode, N: n, Round: round,
		WindowMS: winMS, HardMS: hardMS, DeadlineMS: ddlMS,
		StartedAt: time.Now().Format(time.RFC3339),
		DialErrors: []string{},
	}
	t0 := time.Now()

	c0 := snapshot()
	m.GoroutinesBefore, m.TargetBefore, m.LbWatcherBefore = c0.total, c0.target, c0.lbWatcher
	writeDump(t, filepath.Join(out, "dump_before.dump.txt"))

	// dump 策略：每个调用都记录计数；完整栈只留前两次与最后一次，
	// 避免 30 个进程 × N=10 时堆出几十 MB 重复栈。
	dumpCall := func(i int) bool { return n <= 2 || i == 1 || i == n }

	for i := 1; i <= n; i++ {
		rec := xuCall{Iter: i}
		b := newXuBal(t0)

		var ctx context.Context
		var cancel context.CancelFunc
		var dlAt time.Time
		if mode == "deadline" {
			ctx, cancel = context.WithTimeout(context.Background(), ddl)
			dlAt = time.Now().Add(ddl)
		} else {
			ctx, cancel = context.WithCancel(context.Background())
		}

		opts := []grpc.DialOption{grpc.WithInsecure(), grpc.WithBalancer(b)}
		if mode != "noblock" {
			opts = append(opts, grpc.WithBlock())
		}

		type dialRes struct {
			conn *grpc.ClientConn
			err  error
			d    time.Duration
		}
		start := time.Now()
		done := make(chan dialRes, 1)
		go func() {
			c, e := grpc.DialContext(ctx, "xu.invalid:443", opts...)
			done <- dialRes{c, e, time.Since(start)}
		}()

		recv := func() (dialRes, bool) {
			select {
			case r := <-done:
				return r, true
			case <-time.After(hard):
				return dialRes{}, false
			}
		}

		if mode == "noblock" {
			// 非阻塞：DialContext 先返回，随后等 lbWatcher 进入循环再主动 Close。
			r, ok := recv()
			rec.ReturnMS = msSince(t0)
			if !ok {
				rec.Notes = append(rec.Notes, "DialContext 未在硬超时内返回")
			} else {
				rec.Returned = true
				rec.ElapsedMS = float64(r.d.Microseconds()) / 1000.0
				rec.ReturnedNilCC = r.conn == nil
				if r.err != nil {
					rec.Err = r.err.Error()
				}
			}
			if !waitReady(b.ready, hard) {
				rec.Notes = append(rec.Notes, "lbWatcher 未进入 Notify 循环")
			}
			rec.Trigger = "close-conn"
			rec.TargetSeenMS = msSince(t0)
			rec.TargetBefore = waitTarget(0, 500*time.Millisecond)
			if dumpCall(i) {
				writeDump(t, filepath.Join(out, fmt.Sprintf("dump_call%02d_before.dump.txt", i)))
			}
			rec.CancelMS = msSince(t0)
			if ok && r.conn != nil {
				r.conn.Close()
			}
		} else {
			// 阻塞模式：确认已经进入 balancer 分支且匿名协程停在 <-doneChan，再触发。
			if !waitReady(b.ready, hard) {
				rec.Notes = append(rec.Notes, "lbWatcher 未进入 Notify 循环，本次不计入目标路径")
			}
			rec.TargetBefore = waitTarget(i, 500*time.Millisecond)
			rec.TargetSeenMS = msSince(t0)
			if dumpCall(i) {
				writeDump(t, filepath.Join(out, fmt.Sprintf("dump_call%02d_before.dump.txt", i)))
			}
			if mode == "deadline" {
				rec.Trigger = "context-deadline"
				rec.CancelMS = float64(dlAt.Sub(t0).Microseconds()) / 1000.0
			} else {
				rec.Trigger = "context-cancel"
				cancel()
				rec.CancelMS = msSince(t0)
			}
			r, ok := recv()
			rec.ReturnMS = msSince(t0)
			if ok {
				rec.Returned = true
				rec.ElapsedMS = float64(r.d.Microseconds()) / 1000.0
				rec.ReturnedNilCC = r.conn == nil
				if r.err != nil {
					rec.Err = r.err.Error()
				}
				// 阻塞模式正常不应返回可用连接；若返回了就关掉，避免污染下一轮。
				if r.conn != nil {
					r.conn.Close()
				}
			} else {
				rec.Notes = append(rec.Notes, "DialContext 未在硬超时内返回")
			}
		}

		// 有上限的观察窗口：按 0 / 1/4 / 1/2 / 1 四个采样点记录目标栈数量。
		prev := time.Duration(0)
		for _, p := range []time.Duration{0, win / 4, win / 2, win} {
			time.Sleep(p - prev)
			prev = p
			rec.TargetSamples = append(rec.TargetSamples, snapshot().target)
		}
		final := snapshot()
		rec.TargetAfter = final.target
		rec.LbWatcherAfter = final.lbWatcher
		rec.GoroutinesAfter = final.total
		if dumpCall(i) {
			writeDump(t, filepath.Join(out, fmt.Sprintf("dump_call%02d_after.dump.txt", i)))
		}

		if rec.Returned {
			m.ReturnedCalls++
		}
		if rec.Err != "" {
			m.DialErrors = append(m.DialErrors, rec.Err)
			if strings.Contains(rec.Err, "context canceled") || strings.Contains(rec.Err, "context deadline exceeded") {
				m.ContextErrors++
			}
		}
		m.PerCall = append(m.PerCall, rec)
		m.Events = append(m.Events, fmt.Sprintf("--- call %d ---", i))
		m.Events = append(m.Events, b.eventsSnapshot()...)
		cancel()
	}

	writeDump(t, filepath.Join(out, "dump_after.dump.txt"))
	cEnd := snapshot()
	m.TargetAfter = cEnd.target
	m.LbWatcherAfter = cEnd.lbWatcher
	m.GoroutinesAfter = cEnd.total
	m.FinishedAt = time.Now().Format(time.RFC3339)

	t.Logf("[xu] side=%s mode=%s N=%d round=%d returned=%d ctxErr=%d target before=%d after=%d lbWatcher after=%d goroutines after=%d",
		side, mode, n, round, m.ReturnedCalls, m.ContextErrors,
		m.TargetBefore, m.TargetAfter, m.LbWatcherAfter, m.GoroutinesAfter)

	blob, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		t.Fatalf("序列化 metrics 失败: %v", err)
	}
	if err := os.WriteFile(filepath.Join(out, "metrics.json"), append(blob, '\n'), 0o644); err != nil {
		t.Fatalf("写 metrics.json 失败: %v", err)
	}
}

func waitReady(ch <-chan struct{}, timeout time.Duration) bool {
	select {
	case <-ch:
		return true
	case <-time.After(timeout):
		return false
	}
}

func msSince(t0 time.Time) float64 {
	return float64(time.Since(t0).Microseconds()) / 1000.0
}

func envStr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func envInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
