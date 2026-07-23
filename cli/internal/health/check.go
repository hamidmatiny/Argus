package health

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"sync"
	"time"
)

// Target is a service health probe.
type Target struct {
	Name string
	URL  string
}

// DefaultTargets probes local compose host ports for ARGUS app services.
func DefaultTargets() []Target {
	return []Target{
		{Name: "simulator", URL: "http://localhost:8091/health"},
		{Name: "ray-ingest", URL: "http://localhost:8092/health"},
		{Name: "stream-processor", URL: "http://localhost:8093/health"},
		{Name: "drift-monitor", URL: "http://localhost:8094/health"},
		{Name: "lakehouse-writer", URL: "http://localhost:8096/health"},
		{Name: "lakehouse-dlq", URL: "http://localhost:8097/health"},
		{Name: "incident-engine", URL: "http://localhost:8098/health"},
		{Name: "api-gateway", URL: "http://localhost:8099/health"},
		{Name: "oncall-reporter", URL: "http://localhost:8100/health"},
		{Name: "mlflow", URL: "http://localhost:5002/health"},
		{Name: "dashboard", URL: "http://localhost:3002/login"},
	}
}

// Result is one probe outcome.
type Result struct {
	Name   string
	URL    string
	OK     bool
	Status int
	Body   string
	Err    string
	MS     int64
}

// Check probes all targets concurrently.
func Check(ctx context.Context, targets []Target, client *http.Client) []Result {
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	out := make([]Result, len(targets))
	var wg sync.WaitGroup
	for i, t := range targets {
		wg.Add(1)
		go func(i int, t Target) {
			defer wg.Done()
			out[i] = probe(ctx, client, t)
		}(i, t)
	}
	wg.Wait()
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

func probe(ctx context.Context, client *http.Client, t Target) Result {
	start := time.Now()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, t.URL, nil)
	if err != nil {
		return Result{Name: t.Name, URL: t.URL, Err: err.Error()}
	}
	res, err := client.Do(req)
	ms := time.Since(start).Milliseconds()
	if err != nil {
		return Result{Name: t.Name, URL: t.URL, Err: err.Error(), MS: ms}
	}
	defer res.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(res.Body, 256))
	ok := res.StatusCode >= 200 && res.StatusCode < 400
	return Result{
		Name:   t.Name,
		URL:    t.URL,
		OK:     ok,
		Status: res.StatusCode,
		Body:   strings.TrimSpace(string(b)),
		MS:     ms,
	}
}

// FormatTable renders a simple status table.
func FormatTable(results []Result) string {
	var b strings.Builder
	fmt.Fprintf(&b, "%-18s %-6s %-8s %s\n", "SERVICE", "OK", "MS", "DETAIL")
	fmt.Fprintf(&b, "%-18s %-6s %-8s %s\n", strings.Repeat("-", 18), "------", "--------", "------")
	for _, r := range results {
		ok := "FAIL"
		if r.OK {
			ok = "ok"
		}
		detail := r.Err
		if detail == "" {
			detail = fmt.Sprintf("%d %s", r.Status, truncate(r.Body, 60))
		}
		fmt.Fprintf(&b, "%-18s %-6s %-8d %s\n", r.Name, ok, r.MS, detail)
	}
	return b.String()
}

func truncate(s string, n int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
