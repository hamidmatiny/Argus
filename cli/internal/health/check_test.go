package health_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/argus-platform/argus/cli/internal/health"
)

func TestCheckAndFormat(t *testing.T) {
	ok := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	t.Cleanup(ok.Close)
	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "down", 503)
	}))
	t.Cleanup(bad.Close)

	results := health.Check(context.Background(), []health.Target{
		{Name: "a", URL: ok.URL},
		{Name: "b", URL: bad.URL},
	}, nil)
	if len(results) != 2 {
		t.Fatalf("len=%d", len(results))
	}
	table := health.FormatTable(results)
	if !strings.Contains(table, "SERVICE") || !strings.Contains(table, "a") {
		t.Fatalf("bad table: %s", table)
	}
	var okCount int
	for _, r := range results {
		if r.OK {
			okCount++
		}
	}
	if okCount != 1 {
		t.Fatalf("okCount=%d results=%+v", okCount, results)
	}
}
