// Package api exposes health, metrics, and REST endpoints for the dashboard.
package api

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/argus-platform/argus/incident-engine/internal/engine"
	"github.com/argus-platform/argus/incident-engine/internal/metrics"
	"github.com/argus-platform/argus/incident-engine/internal/webhook"
)

// Server is the HTTP surface for incident-engine.
type Server struct {
	corr     *engine.Correlator
	webhooks *webhook.Dispatcher
	ready    func() bool
	started  time.Time
}

// New constructs the API server.
func New(corr *engine.Correlator, webhooks *webhook.Dispatcher, ready func() bool) *Server {
	return &Server{corr: corr, webhooks: webhooks, ready: ready, started: time.Now().UTC()}
}

// Handler returns the root mux.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/healthz", s.handleHealth)
	mux.HandleFunc("/readyz", s.handleReady)
	mux.Handle("/metrics", metrics.Handler())
	mux.HandleFunc("/breakers", s.handleBreakers)
	mux.HandleFunc("GET /incidents", s.handleIncidents)
	mux.HandleFunc("POST /incidents/{id}/acknowledge", s.handleAcknowledgeIncident)
	mux.HandleFunc("POST /incidents/{id}/resolve", s.handleResolveIncident)
	mux.HandleFunc("/webhooks/mock", s.handleMockWebhook)
	mux.HandleFunc("/webhooks/mock/inbox", s.handleMockInbox)
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"service": "incident-engine",
		"uptime":  time.Since(s.started).String(),
	})
}

func (s *Server) handleReady(w http.ResponseWriter, _ *http.Request) {
	if s.ready != nil && !s.ready() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"ready": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ready": true})
}

func (s *Server) handleBreakers(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"breakers": s.corr.ListBreakers(),
	})
}

func (s *Server) handleIncidents(w http.ResponseWriter, r *http.Request) {
	status := r.URL.Query().Get("status")
	writeJSON(w, http.StatusOK, map[string]any{
		"incidents": s.corr.ListIncidents(status),
	})
}

func (s *Server) handleAcknowledgeIncident(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var body struct {
		Note string `json:"note"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	rec, err := s.corr.AcknowledgeIncident(id, body.Note)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"incident": rec})
}

func (s *Server) handleResolveIncident(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	rec, err := s.corr.ResolveIncident(id)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeJSON(w, http.StatusNotFound, map[string]any{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"incident": rec})
}

func (s *Server) handleMockWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var payload map[string]any
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	s.webhooks.RecordMock(payload)
	slog.Info("mock_webhook_received", "keys", len(payload))
	writeJSON(w, http.StatusAccepted, map[string]any{"accepted": true})
}

func (s *Server) handleMockInbox(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"inbox": s.webhooks.MockInbox()})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
