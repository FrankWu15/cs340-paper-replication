// etcd#6278 驱动器：已存在 "testa" 时在 "test" 前缀上竞选
// buggy 版本会等错 key，Campaign 直到 ctx 超时；fixed 版本立即成功。
package main

import (
	"context"
	"fmt"
	"time"

	"github.com/coreos/etcd/clientv3"
	"github.com/coreos/etcd/clientv3/concurrency"
)

func main() {
	cli, err := clientv3.New(clientv3.Config{
		Endpoints:   []string{"127.0.0.1:23791"},
		DialTimeout: 3 * time.Second,
	})
	if err != nil {
		fmt.Println("DIAL_FAIL:", err)
		return
	}
	defer cli.Close()

	// 放一个以 "test" 为前缀的既有 key —— bug 的触发条件
	if _, err := cli.Put(context.TODO(), "testa", "value"); err != nil {
		fmt.Println("PUT_FAIL:", err)
		return
	}

	s, err := concurrency.NewSession(cli)
	if err != nil {
		fmt.Println("SESSION_FAIL:", err)
		return
	}
	defer s.Close()

	e := concurrency.NewElection(s, "test")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	start := time.Now()
	if err := e.Campaign(ctx, "abc"); err != nil {
		fmt.Printf("CAMPAIGN_FAIL after %.2fs: %v\n", time.Since(start).Seconds(), err)
		return
	}
	fmt.Printf("CAMPAIGN_OK after %.2fs\n", time.Since(start).Seconds())
}
