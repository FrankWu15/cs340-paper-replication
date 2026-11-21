// goast 统计一个 Go 仓库中 goroutine 创建点与并发原语的使用次数，
// 用于复现论文 Table 2（goroutine 创建点）与 Table 4（并发原语使用）。
//
// 用法:
//
//	go run ./tools/goast -root ../vendor/etcd -json ../out/static_etcd.json
//
// 口径说明见 config/apps.yaml 的 static_rules；论文未公开其工具，
// 这里是"同方法重实现"，口径一旦冻结就不要改，否则数字不可比。
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// Counts 对应论文 Table 2 / Table 4 的列。
type Counts struct {
	GoStmtNormal    int `json:"go_stmt_normal"`    // 用普通函数创建 goroutine
	GoStmtAnonymous int `json:"go_stmt_anonymous"` // 用匿名函数创建 goroutine
	Mutex           int `json:"mutex"`             // 严格口径：能推断出接收者是 Mutex/RWMutex 的调用
	LockCalls       int `json:"lock_calls"`        // 机械口径：.Lock/.Unlock/.RLock/.RUnlock 调用点，不看接收者类型
	Atomic          int `json:"atomic"`
	Once            int `json:"once"`
	WaitGroup       int `json:"waitgroup"`
	Cond            int `json:"cond"`
	ChanMake        int `json:"chan_make"`
	ChanSend        int `json:"chan_send"`
	ChanRecv        int `json:"chan_recv"`
	Select          int `json:"select"`
	MiscPool        int `json:"misc_pool"`    // 论文 Misc 列的口径：sync.Pool 引用点
	MiscContext     int `json:"misc_context"` // 诊断用：context.* 调用点（不是论文口径）
	Files           int `json:"files"`
	Lines           int `json:"lines"`
	ParseErrors     int `json:"parse_errors"`
	// 解析失败的文件及原因。必须留痕：静默计数会让"少量失败"永远查不出根因。
	ParseErrorFiles []string `json:"parse_error_files,omitempty"`
	Root            string   `json:"root"`
}

// Chan 总量；论文的 chan 列应与此对应（口径见 config）。
func (c Counts) Chan() int { return c.ChanMake + c.ChanSend + c.ChanRecv }

type stringList []string

func (s *stringList) String() string { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error {
	*s = append(*s, v)
	return nil
}

// ---------- 类型推断（轻量启发式，不做 full type-check） ----------

// kindOf 把表达式映射到原语类别：mutex / once / waitgroup / cond / atomic / misc。
func kindOf(e ast.Expr) string {
	sel, ok := e.(*ast.SelectorExpr)
	if !ok {
		return ""
	}
	pkg, ok := sel.X.(*ast.Ident)
	if !ok {
		return ""
	}
	switch pkg.Name {
	case "sync":
		switch sel.Sel.Name {
		case "Mutex", "RWMutex":
			return "mutex"
		case "Once":
			return "once"
		case "WaitGroup":
			return "waitgroup"
		case "Cond":
			return "cond"
		}
	case "atomic":
		return "atomic"
	case "context":
		return "misc"
	}
	// 自研包装类型：cockroachdb 把标准库的锁全包了一层
	// （pkg/util/syncutil.Mutex，全仓 165 处，而 sync.Mutex 只有 1 处），
	// 只认 "sync" 包名会让它的锁统计直接归零。这里按类型名兜底。
	switch sel.Sel.Name {
	case "Mutex", "RWMutex":
		return "mutex"
	case "Once":
		return "once"
	case "WaitGroup":
		return "waitgroup"
	case "Cond":
		return "cond"
	}
	return ""
}

// isLockMethod 判断方法名是否属于锁操作。
func isLockMethod(s string) bool {
	return s == "Lock" || s == "Unlock" || s == "RLock" || s == "RUnlock"
}

// collectHints 收集变量名 → 原语类别。覆盖 var 声明、:= 复合字面量、结构体字段。
func collectHints(f *ast.File, hints map[string]string) {
	ast.Inspect(f, func(n ast.Node) bool {
		switch x := n.(type) {
		case *ast.ValueSpec: // var wg sync.WaitGroup
			if x.Type != nil {
				if k := kindOf(x.Type); k != "" {
					for _, nm := range x.Names {
						hints[nm.Name] = k
					}
				}
			}
			// wg := sync.WaitGroup{}
			for i, nm := range x.Names {
				if i < len(x.Values) {
					if cl, ok := x.Values[i].(*ast.CompositeLit); ok {
						if k := kindOf(cl.Type); k != "" {
							hints[nm.Name] = k
						}
					}
					if ue, ok := x.Values[i].(*ast.UnaryExpr); ok { // &sync.WaitGroup{}
						if cl, ok := ue.X.(*ast.CompositeLit); ok {
							if k := kindOf(cl.Type); k != "" {
								hints[nm.Name] = k
							}
						}
					}
				}
			}
		case *ast.StructType: // 字段：wg sync.WaitGroup
			if x.Fields != nil {
				for _, fld := range x.Fields.List {
					if fld.Type == nil {
						continue
					}
					if k := kindOf(fld.Type); k != "" {
						for _, nm := range fld.Names {
							hints[nm.Name] = k
						}
					}
				}
			}
		}
		return true
	})
}

// recvName 取调用接收者的名字：wg.Add -> "wg"；x.wg.Add -> "wg"。
func recvName(e ast.Expr) string {
	switch v := e.(type) {
	case *ast.Ident:
		return v.Name
	case *ast.SelectorExpr:
		return v.Sel.Name
	case *ast.StarExpr:
		return recvName(v.X)
	case *ast.ParenExpr:
		return recvName(v.X)
	}
	return ""
}

// ---------- 计数 ----------

func count(f *ast.File, hints map[string]string, c *Counts) {
	ast.Inspect(f, func(n ast.Node) bool {
		switch x := n.(type) {
		case *ast.GoStmt:
			if _, ok := x.Call.Fun.(*ast.FuncLit); ok {
				c.GoStmtAnonymous++
			} else {
				c.GoStmtNormal++
			}
			return true

		case *ast.SendStmt:
			c.ChanSend++

		case *ast.UnaryExpr:
			if x.Op == token.ARROW {
				c.ChanRecv++
			}

		case *ast.SelectStmt:
			c.Select++

		case *ast.CallExpr:
			switch fn := x.Fun.(type) {
			case *ast.Ident:
				if fn.Name == "make" && len(x.Args) > 0 {
					if _, ok := x.Args[0].(*ast.ChanType); ok {
						c.ChanMake++
					}
				}
			case *ast.SelectorExpr:
				method := fn.Sel.Name
				// 机械口径：不看接收者，凡锁方法调用都记一次。
				// 这条对包装类型、内嵌 mutex、跨文件定义都成立，可用 grep 复核。
				if isLockMethod(method) {
					c.LockCalls++
				}
				// 变量/字段上的方法调用：靠 hints 消歧。
				// 必须先查 hints 再判包名——mu.Lock() 的接收者本身也是 *ast.Ident，
				// 若先走包名分支并 return，所有直接对局部变量加锁的调用都会被吞掉。
				switch hints[recvName(fn.X)] {
				case "mutex":
					if isLockMethod(method) {
						c.Mutex++
					}
					return true
				case "waitgroup":
					switch method {
					case "Add", "Done", "Wait":
						c.WaitGroup++
					}
					return true
				case "cond":
					switch method {
					case "Wait", "Signal", "Broadcast":
						c.Cond++
					}
					return true
				case "once":
					if method == "Do" {
						c.Once++
					}
					return true
				}
				if pkg, ok := fn.X.(*ast.Ident); ok {
					switch pkg.Name {
					case "atomic":
						c.Atomic++
					case "context":
						c.MiscContext++
					}
				}
			}

		case *ast.SelectorExpr:
			// 论文 Table 4 的 Misc 列 = sync.Pool。
			// 证据：etcd 该列为 0（而 etcd 有 277 处 context，排除 context 口径），
			// 且 boltdb=2、docker=14 与本口径逐个吻合。详见 out/table2_table4_compare.md。
			if id, ok := x.X.(*ast.Ident); ok && id.Name == "sync" && x.Sel.Name == "Pool" {
				c.MiscPool++
			}
		}
		return true
	})
}

func main() {
	root := flag.String("root", ".", "仓库根目录")
	out := flag.String("json", "", "输出 JSON 路径，空则打印到 stdout")
	includeTests := flag.Bool("include-tests", false, "是否统计 *_test.go（论文口径未知，默认排除）")
	includeVendor := flag.Bool("include-vendor", false, "是否统计 vendor/（论文的 LOC 分母含 vendor，创建点分子是否含 vendor 待核，故留开关）")
	var skips stringList
	flag.Var(&skips, "skip", "额外跳过的目录名，可重复（vendor 默认跳过）")
	flag.Parse()

	skipSet := map[string]bool{"vendor": true, ".git": true, "third_party": true}
	if *includeVendor {
		delete(skipSet, "vendor")
	}
	for _, s := range skips {
		skipSet[s] = true
	}

	c := Counts{Root: *root}
	fset := token.NewFileSet()

	err := filepath.WalkDir(*root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			fmt.Fprintf(os.Stderr, "[walk] %v\n", err)
			if d != nil && d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if d.IsDir() {
			if skipSet[d.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") {
			return nil
		}
		if !*includeTests && strings.HasSuffix(path, "_test.go") {
			return nil
		}
		src, rerr := os.ReadFile(path)
		if rerr != nil {
			fmt.Fprintf(os.Stderr, "[read] %s: %v\n", path, rerr)
			c.ParseErrors++
			c.ParseErrorFiles = append(c.ParseErrorFiles, path+": read: "+rerr.Error())
			return nil
		}
		c.Lines += strings.Count(string(src), "\n") + 1

		f, perr := parser.ParseFile(fset, path, src, parser.SkipObjectResolution)
		if perr != nil {
			c.ParseErrors++
			c.ParseErrorFiles = append(c.ParseErrorFiles, path+": parse: "+perr.Error())
			fmt.Fprintf(os.Stderr, "[parse] %s: %v\n", path, perr)
			return nil
		}
		c.Files++
		hints := make(map[string]string)
		collectHints(f, hints)
		count(f, hints, &c)
		return nil
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "walk error: %v\n", err)
		os.Exit(1)
	}

	buf, _ := json.MarshalIndent(c, "", "  ")
	if *out == "" {
		fmt.Println(string(buf))
		return
	}
	if werr := os.WriteFile(*out, buf, 0o644); werr != nil {
		fmt.Fprintf(os.Stderr, "write error: %v\n", werr)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "files=%d lines=%d goroutine_sites=%d mutex=%d lock_calls=%d chan=%d\n",
		c.Files, c.Lines, c.GoStmtNormal+c.GoStmtAnonymous, c.Mutex, c.LockCalls, c.Chan())
}
