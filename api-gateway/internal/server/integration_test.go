package server_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	goruntime "runtime"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/argus-platform/argus/api-gateway/internal/authz"
	"github.com/argus-platform/argus/api-gateway/internal/config"
	"github.com/argus-platform/argus/api-gateway/internal/middleware"
	"github.com/argus-platform/argus/api-gateway/internal/ratelimit"
	"github.com/argus-platform/argus/api-gateway/internal/service"
	"github.com/argus-platform/argus/api-gateway/internal/upstream"
	argusv1 "github.com/argus-platform/argus/shared/gen/go/argus/v1"
	gwruntime "github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"google.golang.org/protobuf/encoding/protojson"
)

func TestIntegrationProxiedEndpoints(t *testing.T) {
	incidents := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/incidents":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"incidents": []map[string]any{{
					"incident_id": "inc-1", "vehicle_id": "VH-1", "severity": "critical",
					"status": "open", "summary": "breaker open", "timestamp": time.Now().UTC().Format(time.RFC3339),
				}},
			})
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/acknowledge"):
			_ = json.NewEncoder(w).Encode(map[string]any{
				"incident": map[string]any{
					"incident_id": "inc-1", "vehicle_id": "VH-1", "severity": "critical",
					"status": "acknowledged", "summary": "breaker open | ack: looking",
				},
			})
		default:
			http.NotFound(w, r)
		}
	}))
	defer incidents.Close()

	trino := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"columns": []map[string]any{{"name": "vehicle_id"}},
			"data":    [][]any{{"VH-1"}},
		})
	}))
	defer trino.Close()

	dagster := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"launchRun": map[string]any{
					"__typename": "LaunchRunSuccess",
					"run":        map[string]any{"id": "run-123", "status": "STARTED"},
				},
			},
		})
	}))
	defer dagster.Close()

	gw := &service.Gateway{
		Trino:     &upstream.TrinoClient{BaseURL: trino.URL, User: "argus", Catalog: "iceberg", Schema: "fleet"},
		Incidents: &upstream.IncidentsClient{BaseURL: incidents.URL},
		Dagster: &upstream.DagsterClient{
			GraphQLURL: dagster.URL, LocationName: "loc", RepositoryName: "repo", JobName: "drift_retrain_job",
		},
	}

	_, file, _, _ := goruntime.Caller(0)
	policyDir := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "policies"))
	opa, err := authz.Load(context.Background(), policyDir)
	if err != nil {
		t.Fatal(err)
	}

	gwmux := gwruntime.NewServeMux(gwruntime.WithMarshalerOption(gwruntime.MIMEWildcard, &gwruntime.JSONPb{
		MarshalOptions:   protojson.MarshalOptions{UseProtoNames: true},
		UnmarshalOptions: protojson.UnmarshalOptions{DiscardUnknown: true},
	}))
	if err := argusv1.RegisterGatewayServiceHandlerServer(context.Background(), gwmux, gw); err != nil {
		t.Fatal(err)
	}
	h := middleware.Chain(gwmux, middleware.Deps{
		AuthDisabled: true,
		OPA:          opa,
		Limiter:      ratelimit.New(100, 100),
	})

	// List incidents
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/incidents", nil)
	req.Header.Set("X-Argus-Role", "viewer")
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("list incidents: %d %s", rr.Code, rr.Body.String())
	}

	// Query telemetry
	rr = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodPost, "/v1/telemetry/query", strings.NewReader(`{"sql":"SELECT 1","limit":1}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Argus-Role", "viewer")
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("query telemetry: %d %s", rr.Code, rr.Body.String())
	}

	// Acknowledge
	rr = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodPost, "/v1/incidents/inc-1/acknowledge", strings.NewReader(`{"note":"looking"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Argus-Role", "operator")
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("acknowledge: %d %s", rr.Code, rr.Body.String())
	}

	// Trigger retraining
	rr = httptest.NewRecorder()
	req = httptest.NewRequest(http.MethodPost, "/v1/retraining:trigger", strings.NewReader(`{"reason":"manual"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Argus-Role", "operator")
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("retrain: %d %s", rr.Code, rr.Body.String())
	}
	body, _ := io.ReadAll(rr.Body)
	if !strings.Contains(string(body), "run-123") {
		t.Fatalf("expected run id in %s", body)
	}

	_ = config.Load() // keep import used for compile smoke
}
