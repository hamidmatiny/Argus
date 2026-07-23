// Package engine correlates QA metrics + raw incidents into circuit-breaker trips.
package engine

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/segmentio/kafka-go"

	"github.com/argus-platform/argus/incident-engine/internal/circuitbreaker"
	"github.com/argus-platform/argus/incident-engine/internal/config"
	kafkabus "github.com/argus-platform/argus/incident-engine/internal/kafka"
	"github.com/argus-platform/argus/incident-engine/internal/metrics"
	"github.com/argus-platform/argus/incident-engine/internal/models"
	"github.com/argus-platform/argus/incident-engine/internal/policy"
	"github.com/argus-platform/argus/incident-engine/internal/webhook"
)

const fleetVehicle = "fleet"

// Correlator is the hot-path orchestrator.
type Correlator struct {
	cfg       config.Config
	policies  *policy.Engine
	breakers  *circuitbreaker.Store
	publisher *kafkabus.Producer
	webhooks  *webhook.Dispatcher
	metrics   *metrics.Collector

	mu               sync.Mutex
	qaRates          map[string]*ringFloat
	qaExceededStreak map[string]int
	incidents        []models.IncidentRecord
}

type ringFloat struct {
	vals []float64
	max  int
}

func newRing(max int) *ringFloat {
	return &ringFloat{max: max, vals: make([]float64, 0, max)}
}

func (r *ringFloat) push(v float64) {
	r.vals = append(r.vals, v)
	if len(r.vals) > r.max {
		r.vals = r.vals[len(r.vals)-r.max:]
	}
}

func (r *ringFloat) mean() float64 {
	if len(r.vals) == 0 {
		return 0
	}
	var s float64
	for _, v := range r.vals {
		s += v
	}
	return s / float64(len(r.vals))
}

func (r *ringFloat) len() int { return len(r.vals) }

// NewCorrelator wires dependencies.
func NewCorrelator(
	cfg config.Config,
	policies *policy.Engine,
	breakers *circuitbreaker.Store,
	publisher *kafkabus.Producer,
	webhooks *webhook.Dispatcher,
	m *metrics.Collector,
) *Correlator {
	return &Correlator{
		cfg:              cfg,
		policies:         policies,
		breakers:         breakers,
		publisher:        publisher,
		webhooks:         webhooks,
		metrics:          m,
		qaRates:          make(map[string]*ringFloat),
		qaExceededStreak: make(map[string]int),
		incidents:        make([]models.IncidentRecord, 0, 128),
	}
}

// HandleQA processes a telemetry.qa_metrics message.
func (c *Correlator) HandleQA(ctx context.Context, msg kafka.Message) error {
	var ev models.QaMetricEvent
	if err := json.Unmarshal(msg.Value, &ev); err != nil {
		return err
	}
	if ev.VehicleID == "" {
		return nil
	}
	c.metrics.IncidentsProcessed.Inc()

	c.mu.Lock()
	ring, ok := c.qaRates[ev.VehicleID]
	if !ok {
		ring = newRing(c.cfg.QAWindowBatches)
		c.qaRates[ev.VehicleID] = ring
	}
	ring.push(ev.QuarantineRate)
	if ev.Exceeded {
		c.qaExceededStreak[ev.VehicleID]++
	} else {
		c.qaExceededStreak[ev.VehicleID] = 0
	}
	rate := ring.mean()
	batches := ring.len()
	streak := c.qaExceededStreak[ev.VehicleID]
	c.mu.Unlock()

	// Fleet-wide drift must not trip every vehicle on QA updates.
	return c.evaluate(ctx, ev.VehicleID, rate, batches, streak, 0)
}

// HandleIncident processes an incidents.raw message.
func (c *Correlator) HandleIncident(ctx context.Context, msg kafka.Message) error {
	var ev models.RawIncident
	if err := json.Unmarshal(msg.Value, &ev); err != nil {
		return err
	}
	c.metrics.IncidentsProcessed.Inc()

	driftCount := int(ev.ObservedValue)
	if len(ev.DriftedFeatures) > driftCount {
		driftCount = len(ev.DriftedFeatures)
	}

	vehicle := ev.VehicleID
	if vehicle == "" {
		vehicle = fleetVehicle
	}

	c.mu.Lock()
	rate := 0.0
	batches := 0
	streak := 0
	if ring, ok := c.qaRates[vehicle]; ok {
		rate = ring.mean()
		batches = ring.len()
	}
	streak = c.qaExceededStreak[vehicle]
	c.mu.Unlock()

	return c.evaluate(ctx, vehicle, rate, batches, streak, driftCount)
}

func (c *Correlator) evaluate(
	ctx context.Context,
	vehicleID string,
	rollingRate float64,
	batchCount, streak, driftCount int,
) error {
	now := time.Now().UTC()
	b := c.breakers.Get(vehicleID)
	in := models.PolicyInput{
		VehicleID:             vehicleID,
		RollingQuarantineRate: rollingRate,
		QAWindowBatches:       c.cfg.QAWindowBatches,
		QABatchCount:          batchCount,
		QARateThreshold:       c.cfg.QARateThreshold,
		DriftedFeatureCount:   driftCount,
		DriftMinFeatures:      c.cfg.DriftMinFeatures,
		ConsecutiveFailures:   streak,
		ConsecutiveFailureMax: c.cfg.ConsecutiveFailMax,
		HourUTC:               now.Hour(),
		Weekday:               int(now.Weekday()),
		BreakerState:          string(b.State),
	}

	dec, latency, err := c.policies.Evaluate(ctx, in)
	if err != nil {
		return err
	}
	c.metrics.PolicyEvalSeconds.Observe(latency.Seconds())

	out := c.breakers.Evaluate(vehicleID, dec.Trip, dec.Reasons)
	c.metrics.SetBreaker(vehicleID, string(out.Breaker.State))

	if out.Recovered {
		n := c.resolveVehicleOpenIncidents(vehicleID, "breaker_recovered")
		slog.Info("circuit_breaker_recovered",
			"vehicle_id", vehicleID,
			"resolved_incidents", n,
		)
	}

	if !out.Tripped {
		return nil
	}

	metricsMap := map[string]any{
		"rolling_quarantine_rate": rollingRate,
		"qa_window_batches":       c.cfg.QAWindowBatches,
		"qa_batch_count":          batchCount,
		"consecutive_failures":    streak,
		"drifted_feature_count":   driftCount,
	}

	esc, isUpdate := c.upsertOpenIncident(vehicleID, dec, metricsMap)

	payload, err := json.Marshal(esc)
	if err != nil {
		return err
	}
	if c.publisher != nil {
		if err := c.publisher.Publish(ctx, []byte(vehicleID), payload); err != nil {
			slog.Error("escalation_publish_failed", "err", err)
		}
	}
	if err := c.webhooks.Deliver(ctx, dec.Route, esc.NotificationChannels); err != nil {
		slog.Warn("webhook_partial_failure", "err", err)
	} else {
		c.metrics.WebhooksDelivered.Inc()
	}
	c.metrics.EscalationsPublished.Inc()

	if isUpdate {
		slog.Warn("circuit_breaker_retrip",
			"vehicle_id", vehicleID,
			"reasons", dec.Reasons,
			"route", dec.Route,
			"incident_id", esc.IncidentID,
			"retrip_count", esc.RetripCount,
		)
	} else {
		slog.Warn("circuit_breaker_tripped",
			"vehicle_id", vehicleID,
			"reasons", dec.Reasons,
			"route", dec.Route,
			"incident_id", esc.IncidentID,
		)
	}
	return nil
}

// upsertOpenIncident creates a fresh episode or refreshes an existing open one
// for vehicleID (including the synthetic "fleet" key). Same incident_id /
// PagerDuty dedup_key across HalfOpen→Open retrips.
func (c *Correlator) upsertOpenIncident(
	vehicleID string,
	dec models.PolicyDecision,
	metricsMap map[string]any,
) (models.EscalatedIncident, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	for i := range c.incidents {
		inc := &c.incidents[i]
		if inc.VehicleID != vehicleID || !inc.Open {
			continue
		}
		webhook.RefreshEscalated(inc, dec, metricsMap, c.cfg.SlackChannel, c.cfg.PagerDutyRoutingKey)
		return inc.EscalatedIncident, true
	}

	esc := webhook.BuildEscalated(
		vehicleID,
		dec,
		metricsMap,
		c.cfg.SlackChannel,
		c.cfg.PagerDutyRoutingKey,
	)
	c.incidents = append(c.incidents, models.IncidentRecord{EscalatedIncident: esc, Open: true})
	if len(c.incidents) > 500 {
		c.incidents = c.incidents[len(c.incidents)-500:]
	}
	return esc, false
}

// resolveVehicleOpenIncidents marks all open incidents for vehicleID resolved.
func (c *Correlator) resolveVehicleOpenIncidents(vehicleID, reason string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now().UTC().Format(time.RFC3339Nano)
	n := 0
	for i := range c.incidents {
		inc := &c.incidents[i]
		if inc.VehicleID != vehicleID || !inc.Open {
			continue
		}
		inc.Open = false
		inc.Status = "resolved"
		inc.ResolvedAt = now
		inc.ResolveReason = reason
		n++
	}
	return n
}

// ResolveIncident manually resolves an incident by ID. Idempotent when already resolved.
func (c *Correlator) ResolveIncident(id string) (models.IncidentRecord, error) {
	if id == "" {
		return models.IncidentRecord{}, fmt.Errorf("incident id required")
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	for i := range c.incidents {
		inc := &c.incidents[i]
		if inc.IncidentID != id {
			continue
		}
		if !inc.Open && inc.Status == "resolved" {
			return *inc, nil
		}
		now := time.Now().UTC().Format(time.RFC3339Nano)
		inc.Open = false
		inc.Status = "resolved"
		inc.ResolvedAt = now
		inc.ResolveReason = "manual"
		return *inc, nil
	}
	return models.IncidentRecord{}, fmt.Errorf("incident %q not found", id)
}

// ListBreakers returns breaker snapshots.
func (c *Correlator) ListBreakers() []circuitbreaker.Breaker {
	return c.breakers.Snapshot()
}

// ListIncidents filters in-memory escalations.
func (c *Correlator) ListIncidents(status string) []models.IncidentRecord {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := make([]models.IncidentRecord, 0, len(c.incidents))
	for _, inc := range c.incidents {
		switch status {
		case "open":
			if inc.Open && inc.Status == "open" {
				out = append(out, inc)
			}
		case "resolved":
			if !inc.Open || inc.Status == "resolved" {
				out = append(out, inc)
			}
		case "":
			out = append(out, inc)
		default:
			if inc.Status == status {
				out = append(out, inc)
			}
		}
	}
	return out
}
