// Package models defines Kafka and API wire types for incident-engine.
package models

import "time"

// QaMetricEvent is published by stream-processor on telemetry.qa_metrics.
type QaMetricEvent struct {
	VehicleID      string    `json:"vehicle_id"`
	WindowSize     int       `json:"window_size"`
	Total          int       `json:"total"`
	Quarantined    int       `json:"quarantined"`
	QuarantineRate float64   `json:"quarantine_rate"`
	Threshold      float64   `json:"threshold"`
	Exceeded       bool      `json:"exceeded"`
	WindowEnd      time.Time `json:"window_end"`
	Type           string    `json:"type"`
}

// RawIncident is the JSON shape on incidents.raw (proto core + extensions).
type RawIncident struct {
	IncidentID      string   `json:"incident_id"`
	Severity        string   `json:"severity"`
	SourceService   string   `json:"source_service"`
	MetricName      string   `json:"metric_name"`
	Threshold       float64  `json:"threshold"`
	ObservedValue   float64  `json:"observed_value"`
	Timestamp       string   `json:"timestamp"`
	Status          string   `json:"status"`
	VehicleID       string   `json:"vehicle_id,omitempty"`
	DriftedFeatures []string `json:"drifted_features,omitempty"`
	WindowSize      int      `json:"window_size,omitempty"`
	Alpha           float64  `json:"alpha,omitempty"`
}

// PolicyInput is the document evaluated by OPA/Rego policies.
type PolicyInput struct {
	VehicleID             string  `json:"vehicle_id"`
	RollingQuarantineRate float64 `json:"rolling_quarantine_rate"`
	QAWindowBatches       int     `json:"qa_window_batches"`
	QABatchCount          int     `json:"qa_batch_count"`
	QARateThreshold       float64 `json:"qa_rate_threshold"`
	DriftedFeatureCount   int     `json:"drifted_feature_count"`
	DriftMinFeatures      int     `json:"drift_min_features"`
	ConsecutiveFailures   int     `json:"consecutive_failures"`
	ConsecutiveFailureMax int     `json:"consecutive_failure_max"`
	HourUTC               int     `json:"hour_utc"`
	Weekday               int     `json:"weekday"` // 0=Sunday … 6=Saturday
	BreakerState          string  `json:"breaker_state"`
}

// PolicyDecision aggregates Rego outputs for one evaluation.
type PolicyDecision struct {
	Trip     bool     `json:"trip"`
	Reasons  []string `json:"reasons"`
	Route    string   `json:"route"` // slack | pagerduty | both
	Severity string   `json:"severity"`
}

// EscalatedIncident is published to incidents.escalated after a trip.
type EscalatedIncident struct {
	IncidentID            string         `json:"incident_id"`
	VehicleID             string         `json:"vehicle_id"`
	Severity              string         `json:"severity"`
	Status                string         `json:"status"`
	Timestamp             string         `json:"timestamp"`
	ResolvedAt            string         `json:"resolved_at,omitempty"`
	CircuitBreakerTripped bool           `json:"circuit_breaker_tripped"`
	Summary               string         `json:"summary"`
	Reasons               []string       `json:"reasons"`
	Route                 string         `json:"route"`
	Metrics               map[string]any `json:"metrics"`
	NotificationChannels  map[string]any `json:"notification_channels"`
}

// IncidentRecord is the in-memory store entry for GET /incidents.
type IncidentRecord struct {
	EscalatedIncident
	Open          bool   `json:"open"`
	ResolveReason string `json:"resolve_reason,omitempty"`
}
