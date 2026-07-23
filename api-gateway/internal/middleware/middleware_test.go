package middleware_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/argus-platform/argus/api-gateway/internal/authz"
	"github.com/argus-platform/argus/api-gateway/internal/middleware"
	"github.com/argus-platform/argus/api-gateway/internal/ratelimit"
)

func policyDir(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("caller")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "policies"))
}

func TestAuthRejectionMissingBearer(t *testing.T) {
	opa, err := authz.Load(context.Background(), policyDir(t))
	if err != nil {
		t.Fatal(err)
	}
	h := middleware.Chain(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}), middleware.Deps{
		AuthDisabled: false,
		OPA:          opa,
		Limiter:      ratelimit.New(100, 100),
		APIKeys:      map[string]string{"k": "admin"},
	})
	req := httptest.NewRequest(http.MethodGet, "/v1/incidents", nil)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("got %d want 401", rr.Code)
	}
}

func TestAPIKeyAuthAndOPADenyViewerWrite(t *testing.T) {
	opa, err := authz.Load(context.Background(), policyDir(t))
	if err != nil {
		t.Fatal(err)
	}
	h := middleware.Chain(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}), middleware.Deps{
		AuthDisabled: false,
		OPA:          opa,
		Limiter:      ratelimit.New(100, 100),
		APIKeys:      map[string]string{"viewer-key": "viewer", "ops-key": "operator"},
	})

	req := httptest.NewRequest(http.MethodPost, "/v1/retraining:trigger", nil)
	req.Header.Set("X-API-Key", "viewer-key")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Fatalf("viewer write got %d want 403", rr.Code)
	}

	req2 := httptest.NewRequest(http.MethodPost, "/v1/retraining:trigger", nil)
	req2.Header.Set("X-API-Key", "ops-key")
	rr2 := httptest.NewRecorder()
	h.ServeHTTP(rr2, req2)
	if rr2.Code != http.StatusOK {
		t.Fatalf("operator write got %d want 200 body=%s", rr2.Code, rr2.Body.String())
	}
}

func TestRateLimitEnforcement(t *testing.T) {
	opa, err := authz.Load(context.Background(), policyDir(t))
	if err != nil {
		t.Fatal(err)
	}
	h := middleware.Chain(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}), middleware.Deps{
		AuthDisabled: true,
		OPA:          opa,
		Limiter:      ratelimit.New(1, 1),
		APIKeys:      map[string]string{},
	})
	req := httptest.NewRequest(http.MethodGet, "/v1/incidents", nil)
	req.Header.Set("X-API-Key", "burst-key")
	req.Header.Set("X-Argus-Role", "viewer")

	rr1 := httptest.NewRecorder()
	h.ServeHTTP(rr1, req)
	if rr1.Code != http.StatusOK {
		t.Fatalf("first request got %d", rr1.Code)
	}
	rr2 := httptest.NewRecorder()
	h.ServeHTTP(rr2, req)
	if rr2.Code != http.StatusTooManyRequests {
		t.Fatalf("second request got %d want 429", rr2.Code)
	}
	var body map[string]any
	_ = json.Unmarshal(rr2.Body.Bytes(), &body)
	if body["error"] != "rate limit exceeded" {
		t.Fatalf("unexpected body %#v", body)
	}
}
