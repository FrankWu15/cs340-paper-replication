// grpc#1459 探针 —— client keepalive 唤醒后未复位 awakenKeepalive，keepalive 协程在持有 t.mu 时
// 阻塞在 <-t.awakenKeepalive 上，此后任何 NewStream 取 t.mu 都会永久挂起。
//
// 判定：第二次 RPC 不返回（go test -timeout 杀掉，栈里能看到 NewStream → sync.Mutex.Lock）。
//
// 放在仓库根目录、package grpc_test，靠公开 API 触发，不改动被测包内部符号。

package grpc_test

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/keepalive"
	testpb "google.golang.org/grpc/test/grpc_testing"
)

type probeTestServer struct{}

func (probeTestServer) EmptyCall(ctx context.Context, in *testpb.Empty) (*testpb.Empty, error) {
	return &testpb.Empty{}, nil
}

func (probeTestServer) UnaryCall(ctx context.Context, in *testpb.SimpleRequest) (*testpb.SimpleResponse, error) {
	return &testpb.SimpleResponse{}, nil
}

func (probeTestServer) StreamingOutputCall(in *testpb.StreamingOutputCallRequest, stream testpb.TestService_StreamingOutputCallServer) error {
	return nil
}

func (probeTestServer) StreamingInputCall(stream testpb.TestService_StreamingInputCallServer) error {
	return nil
}

func (probeTestServer) FullDuplexCall(stream testpb.TestService_FullDuplexCallServer) error {
	return nil
}

func (probeTestServer) HalfDuplexCall(stream testpb.TestService_HalfDuplexCallServer) error {
	return nil
}

func TestKeepaliveAwakenDeadlockProbe(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	s := grpc.NewServer()
	testpb.RegisterTestServiceServer(s, probeTestServer{})
	go s.Serve(lis)
	defer s.Stop()

	// keepalive.Time 调小，让 keepalive 协程在几轮 tick 内就进入 dormant 分支
	cc, err := grpc.Dial(lis.Addr().String(), grpc.WithInsecure(),
		grpc.WithKeepaliveParams(keepalive.ClientParameters{
			Time:    100 * time.Millisecond,
			Timeout: 100 * time.Millisecond,
		}))
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer cc.Close()

	c := testpb.NewTestServiceClient(cc)

	// 第一次 RPC 唤醒 keepalive；此后每一轮「失效的唤醒令牌」都会让 keepalive 协程在持 t.mu 时
	// 阻塞在 <-awakenKeepalive 上。第 2 次 RPC 仍能返回，第 3 次开始卡在 NewStream 的 t.mu.Lock。
	for i := 1; i <= 4; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		if _, err := c.EmptyCall(ctx, &testpb.Empty{}); err != nil {
			cancel()
			t.Fatalf("RPC #%d: %v", i, err)
		}
		cancel()
		t.Logf("RPC #%d returned", i)
		time.Sleep(700 * time.Millisecond)
	}
	t.Logf("4 次 RPC 全部返回：未触发死锁")
}
