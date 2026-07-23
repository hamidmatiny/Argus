package authz_test

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/argus-platform/argus/api-gateway/internal/authz"
)

func TestOPARoles(t *testing.T) {
	_, file, _, _ := runtime.Caller(0)
	dir := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "policies"))
	eng, err := authz.Load(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		role, method, path string
		want               bool
	}{
		{"viewer", "GET", "/v1/incidents", true},
		{"viewer", "POST", "/v1/telemetry/query", true},
		{"viewer", "POST", "/v1/retraining:trigger", false},
		{"viewer", "POST", "/v1/incidents/abc/acknowledge", false},
		{"operator", "POST", "/v1/retraining:trigger", true},
		{"operator", "POST", "/v1/incidents/abc/acknowledge", true},
		{"admin", "DELETE", "/v1/anything", true},
	}
	for _, tc := range cases {
		got, err := eng.Allow(context.Background(), authz.Input{Role: tc.role, Method: tc.method, Path: tc.path})
		if err != nil {
			t.Fatalf("%+v: %v", tc, err)
		}
		if got != tc.want {
			t.Fatalf("%+v: got %v want %v", tc, got, tc.want)
		}
	}
}
