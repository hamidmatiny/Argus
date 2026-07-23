// Package webhook delivers Slack/PagerDuty-shaped alerts and a local mock sink.
package webhook

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/argus-platform/argus/incident-engine/internal/models"
)

// Dispatcher posts notification channel payloads to configured webhooks.
type Dispatcher struct {
	client       *http.Client
	slackURL     string
	pagerDutyURL string
	mockURL      string
	mu           sync.Mutex
	mockInbox    []map[string]any
}

// NewDispatcher constructs a dispatcher. Empty URLs are skipped unless mockURL is set.
func NewDispatcher(slackURL, pagerDutyURL, mockURL string) *Dispatcher {
	return &Dispatcher{
		client:       &http.Client{Timeout: 5 * time.Second},
		slackURL:     slackURL,
		pagerDutyURL: pagerDutyURL,
		mockURL:      mockURL,
		mockInbox:    make([]map[string]any, 0, 32),
	}
}

// Deliver sends channel payloads according to route (slack|pagerduty|both).
func (d *Dispatcher) Deliver(ctx context.Context, route string, channels map[string]any) error {
	targets := map[string]string{}
	switch route {
	case "pagerduty":
		targets["pagerduty"] = firstNonEmpty(d.pagerDutyURL, d.mockURL)
	case "both":
		targets["slack"] = firstNonEmpty(d.slackURL, d.mockURL)
		targets["pagerduty"] = firstNonEmpty(d.pagerDutyURL, d.mockURL)
	default: // slack
		targets["slack"] = firstNonEmpty(d.slackURL, d.mockURL)
	}

	var firstErr error
	for channel, url := range targets {
		if url == "" {
			continue
		}
		body, ok := channels[channel]
		if !ok {
			continue
		}
		if err := d.postJSON(ctx, url, body); err != nil {
			slog.Error("webhook_delivery_failed", "channel", channel, "err", err)
			if firstErr == nil {
				firstErr = err
			}
		} else {
			slog.Info("webhook_delivered", "channel", channel, "url", url)
		}
	}
	return firstErr
}

// RecordMock is used by the in-process mock HTTP handler.
func (d *Dispatcher) RecordMock(payload map[string]any) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.mockInbox = append(d.mockInbox, payload)
	if len(d.mockInbox) > 200 {
		d.mockInbox = d.mockInbox[len(d.mockInbox)-200:]
	}
}

// MockInbox returns a copy of recorded mock webhook payloads.
func (d *Dispatcher) MockInbox() []map[string]any {
	d.mu.Lock()
	defer d.mu.Unlock()
	out := make([]map[string]any, len(d.mockInbox))
	copy(out, d.mockInbox)
	return out
}

func (d *Dispatcher) postJSON(ctx context.Context, url string, payload any) error {
	buf, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(buf))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := d.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("webhook status %d", resp.StatusCode)
	}
	return nil
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

// BuildEscalated constructs a fresh incidents.escalated document (new episode).
func BuildEscalated(
	vehicleID string,
	dec models.PolicyDecision,
	metrics map[string]any,
	slackChannel, pdKey string,
) models.EscalatedIncident {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	esc := models.EscalatedIncident{
		IncidentID:            fmt.Sprintf("esc_%s_%d", vehicleID, time.Now().UTC().UnixNano()),
		VehicleID:             vehicleID,
		Severity:              dec.Severity,
		Status:                "open",
		Timestamp:             now,
		LastUpdatedAt:         now,
		CircuitBreakerTripped: true,
		Summary: fmt.Sprintf(
			"Circuit breaker tripped for %s: %s",
			vehicleID,
			joinReasons(dec.Reasons),
		),
		Reasons: dec.Reasons,
		Route:   dec.Route,
		Metrics: metrics,
	}
	esc.NotificationChannels = BuildChannels(esc, slackChannel, pdKey)
	return esc
}

// RefreshEscalated updates an existing open incident in place (retrip / continuation).
// Keeps IncidentID and Timestamp (first-triggered-at); bumps LastUpdatedAt and RetripCount.
func RefreshEscalated(
	existing *models.IncidentRecord,
	dec models.PolicyDecision,
	metrics map[string]any,
	slackChannel, pdKey string,
) {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	existing.RetripCount++
	existing.LastUpdatedAt = now
	existing.Severity = dec.Severity
	existing.Route = dec.Route
	existing.Reasons = append([]string(nil), dec.Reasons...)
	existing.Metrics = metrics
	existing.Summary = fmt.Sprintf(
		"Circuit breaker still open for %s (retrip %d): %s",
		existing.VehicleID,
		existing.RetripCount,
		joinReasons(dec.Reasons),
	)
	existing.Status = "open"
	existing.Open = true
	existing.NotificationChannels = BuildChannels(existing.EscalatedIncident, slackChannel, pdKey)
}

func joinReasons(reasons []string) string {
	if len(reasons) == 0 {
		return "policy trip"
	}
	return fmt.Sprintf("%v", reasons)
}
