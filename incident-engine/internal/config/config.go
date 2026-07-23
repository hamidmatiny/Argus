// Package config loads incident-engine settings from the environment.
package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds runtime settings for the incident-engine service.
type Config struct {
	HTTPAddr            string
	KafkaBrokers        []string
	KafkaGroupID        string
	QAMetricsTopic      string
	IncidentsRawTopic   string
	EscalatedTopic      string
	PolicyDir           string
	QAWindowBatches     int
	QARateThreshold     float64
	DriftMinFeatures    int
	ConsecutiveFailMax  int
	OpenCooldown        time.Duration
	HalfOpenSuccessNeed int
	SlackWebhookURL     string
	PagerDutyWebhookURL string
	SlackChannel        string
	PagerDutyRoutingKey string
	EnableMockWebhook   bool
}

// Load reads configuration from environment variables.
func Load() Config {
	return Config{
		HTTPAddr:            getenv("INCIDENT_ENGINE_ADDR", ":8098"),
		KafkaBrokers:        splitCSV(getenv("KAFKA_BROKERS", "localhost:19092")),
		KafkaGroupID:        getenv("INCIDENT_ENGINE_KAFKA_GROUP_ID", "argus-incident-engine"),
		QAMetricsTopic:      getenv("QA_METRICS_TOPIC", "telemetry.qa_metrics"),
		IncidentsRawTopic:   getenv("INCIDENTS_RAW_TOPIC", "incidents.raw"),
		EscalatedTopic:      getenv("INCIDENTS_ESCALATED_TOPIC", "incidents.escalated"),
		PolicyDir:           getenv("INCIDENT_POLICY_DIR", "policies"),
		QAWindowBatches:     getenvInt("INCIDENT_QA_WINDOW_BATCHES", 5),
		QARateThreshold:     getenvFloat("INCIDENT_QA_RATE_THRESHOLD", 0.15),
		DriftMinFeatures:    getenvInt("INCIDENT_DRIFT_MIN_FEATURES", 2),
		ConsecutiveFailMax:  getenvInt("INCIDENT_CONSECUTIVE_FAILURES", 3),
		OpenCooldown:        time.Duration(getenvInt("INCIDENT_OPEN_COOLDOWN_SEC", 60)) * time.Second,
		HalfOpenSuccessNeed: getenvInt("INCIDENT_HALF_OPEN_SUCCESS", 1),
		SlackWebhookURL:     os.Getenv("INCIDENT_SLACK_WEBHOOK_URL"),
		PagerDutyWebhookURL: os.Getenv("INCIDENT_PAGERDUTY_WEBHOOK_URL"),
		SlackChannel:        getenv("INCIDENT_SLACK_CHANNEL", "#argus-alerts"),
		PagerDutyRoutingKey: getenv("INCIDENT_PAGERDUTY_ROUTING_KEY", "argus-production"),
		EnableMockWebhook:   getenvBool("INCIDENT_ENABLE_MOCK_WEBHOOK", true),
	}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func getenvFloat(key string, fallback float64) float64 {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return fallback
	}
	return f
}

func getenvBool(key string, fallback bool) bool {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return fallback
	}
	return b
}

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
