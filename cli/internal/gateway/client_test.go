package gateway_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/argus-platform/argus/cli/internal/gateway"
)

func TestListIncidentsAndAck(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/incidents", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "demo-operator" {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"incidents": []map[string]string{
				{"incident_id": "esc_1", "vehicle_id": "VH-1", "status": "INCIDENT_STATUS_OPEN"},
			},
		})
	})
	mux.HandleFunc("/v1/incidents/esc_1/acknowledge", func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if !strings.Contains(string(body), "note") {
			http.Error(w, "bad body", http.StatusBadRequest)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"incident": map[string]string{
				"incident_id": "esc_1",
				"status":      "INCIDENT_STATUS_ACKNOWLEDGED",
			},
		})
	})
	mux.HandleFunc("/v1/retraining:trigger", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]string{
			"run_id": "run-9", "status": "STARTED", "message": "ok",
		})
	})
	mux.HandleFunc("/v1/telemetry/stream", func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "no flush", 500)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte("{\"event\":{\"vehicle_id\":\"VH-1\"}}\n"))
		flusher.Flush()
		_, _ = w.Write([]byte("{\"event\":{\"vehicle_id\":\"VH-2\"}}\n"))
		flusher.Flush()
	})

	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)

	c := &gateway.Client{BaseURL: srv.URL, APIKey: "demo-operator"}
	ctx := context.Background()

	items, err := c.ListIncidents(ctx, "open")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].IncidentID != "esc_1" {
		t.Fatalf("unexpected list: %+v", items)
	}

	inc, err := c.Acknowledge(ctx, "esc_1", "hi")
	if err != nil {
		t.Fatal(err)
	}
	if inc.Status != "INCIDENT_STATUS_ACKNOWLEDGED" {
		t.Fatalf("ack status: %s", inc.Status)
	}

	re, err := c.TriggerRetrain(ctx, "test")
	if err != nil {
		t.Fatal(err)
	}
	if re.RunID != "run-9" {
		t.Fatalf("retrain: %+v", re)
	}

	ctx2, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	var n int
	err = c.StreamTelemetry(ctx2, "", func(line []byte) error {
		n++
		if n >= 2 {
			cancel()
		}
		return nil
	})
	if n < 2 {
		t.Fatalf("expected >=2 stream lines, got %d (err=%v)", n, err)
	}
}
