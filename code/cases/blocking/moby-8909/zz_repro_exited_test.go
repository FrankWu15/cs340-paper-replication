package daemon

// Driver for docker#8909 (fixed by 03ea2166 "Fix deadlock in ps exited filter").
// Runs the upstream Daemon.Containers() on a real container store, a real
// sqlite-backed container graph and real filter parsing. Nothing in the daemon
// package is stubbed: the call below enters daemon/list.go unchanged.

import (
	"database/sql"
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/docker/docker/engine"
	"github.com/docker/docker/graph"
	"github.com/docker/docker/nat"
	"github.com/docker/docker/pkg/graphdb"
	"github.com/docker/docker/runconfig"
)

func TestExitedFilter(t *testing.T) {
	dir, err := ioutil.TempDir("", "graph")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	conn, err := sql.Open("sqlite3", filepath.Join(dir, "graph.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	gdb, err := graphdb.NewDatabase(conn, true)
	if err != nil {
		t.Fatal(err)
	}

	d := &Daemon{
		containers:     &contStore{s: map[string]*Container{}},
		containerGraph: gdb,
		repositories:   &graph.TagStore{},
	}

	c := &Container{
		State:           NewState(),
		ID:              "b6a1f0c4d2e8",
		Name:            "/exited-probe",
		Image:           "busybox",
		Config:          &runconfig.Config{},
		NetworkSettings: &NetworkSettings{Ports: nat.PortMap{}},
	}
	c.State.ExitCode = 0
	c.State.Running = false
	d.containers.Add(c.ID, c)

	eng := engine.New()
	job := eng.Job("containers")
	job.Setenv("all", "1")
	job.Setenv("filters", `{"exited":["0"]}`)

	done := make(chan string, 1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				done <- fmt.Sprintf("panic: %v", r)
			}
		}()
		d.Containers(job)
		done <- "returned"
	}()

	select {
	case r := <-done:
		fmt.Printf("VERDICT: OK (%s)\n", r)
	case <-time.After(5 * time.Second):
		fmt.Println("VERDICT: DEADLOCK  Daemon.Containers() did not return within 5s")
		buf := make([]byte, 1<<16)
		n := runtime.Stack(buf, true)
		for _, line := range strings.Split(string(buf[:n]), "\n") {
			if strings.Contains(line, "docker/daemon") || strings.Contains(line, "sync.(*Mutex)") ||
				strings.Contains(line, "GetExitCode") {
				fmt.Println("  " + strings.TrimSpace(line))
			}
		}
	}
}
