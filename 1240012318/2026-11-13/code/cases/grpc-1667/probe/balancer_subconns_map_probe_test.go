// grpc#1667 探针 —— ccBalancerWrapper.subConns 这个 map 在读（watcher 的关闭分支 for-range）
// 与写（NewSubConn / RemoveSubConn）之间没有任何同步。
//
// 触发方式：自定义 balancer 起若干条 goroutine 同时对同一张 map 增删 SubConn，
// 主 goroutine 随后 cc.Close()，让 watcher 的关闭分支在遍历 map 时也被并发写入。
//
// 判定（-race）：WARNING: DATA RACE，或 fatal error: concurrent map writes / iteration and map write。
// fixed 侧补上了 ccb.mu，同样的操作序列应当干净通过。

package grpc_test

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/balancer"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/resolver"
)

type churnBalancer struct {
	cc      balancer.ClientConn
	stop    chan struct{}
	started int32
}

type churnBuilder struct {
	mu sync.Mutex
	lb *churnBalancer
}

func (b *churnBuilder) balancer() *churnBalancer {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.lb
}

func (b *churnBuilder) Build(cc balancer.ClientConn, opts balancer.BuildOptions) balancer.Balancer {
	lb := &churnBalancer{cc: cc, stop: make(chan struct{})}
	b.mu.Lock()
	b.lb = lb
	b.mu.Unlock()
	return lb
}

func (b *churnBuilder) Name() string { return "probe_churn" }

func (lb *churnBalancer) HandleSubConnStateChange(sc balancer.SubConn, s connectivity.State) {}

func (lb *churnBalancer) HandleResolvedAddrs(addrs []resolver.Address, err error) {
	if err != nil || len(addrs) == 0 {
		return
	}
	if !atomic.CompareAndSwapInt32(&lb.started, 0, 1) {
		return
	}
	// 先铺几条，保证关闭分支的 for-range 有东西可遍历
	for i := 0; i < 8; i++ {
		if _, err := lb.cc.NewSubConn(addrs, balancer.NewSubConnOptions{}); err != nil {
			return
		}
	}
	// 4 条 goroutine 并发增删同一张 map：写-写本身就是数据竞态
	for i := 0; i < 4; i++ {
		go lb.churn(addrs)
	}
}

func (lb *churnBalancer) churn(addrs []resolver.Address) {
	for {
		select {
		case <-lb.stop:
			return
		default:
		}
		sc, err := lb.cc.NewSubConn(addrs, balancer.NewSubConnOptions{})
		if err != nil {
			continue
		}
		lb.cc.RemoveSubConn(sc)
	}
}

func (lb *churnBalancer) Close() {
	// 故意不关 stop：让 churn 在 ClientConn 关闭、watcher 遍历 map 时仍在写
}

func TestBalancerSubConnsMapRaceProbe(t *testing.T) {
	b := &churnBuilder{}
	cc, err := grpc.Dial("127.0.0.1:65000", grpc.WithInsecure(), grpc.WithBalancerBuilder(b))
	if err != nil {
		t.Fatalf("dial: %v", err)
	}

	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		if lb := b.balancer(); lb != nil && atomic.LoadInt32(&lb.started) == 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	lb := b.balancer()
	if lb == nil || atomic.LoadInt32(&lb.started) != 1 {
		t.Fatalf("balancer 未收到地址，探针无效")
	}

	time.Sleep(500 * time.Millisecond) // 让 churn 跑起来
	cc.Close()                         // watcher 在关闭分支里 range subConns
	time.Sleep(1500 * time.Millisecond)
}
