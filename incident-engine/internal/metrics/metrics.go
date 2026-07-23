// Package metrics exposes Prometheus instrumentation for incident-engine.
package metrics

import (
	"net/http"
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Collector holds Prometheus metrics.
type Collector struct {
	IncidentsProcessed   prometheus.Counter
	EscalationsPublished prometheus.Counter
	PolicyEvalSeconds    prometheus.Histogram
	BreakerState         *prometheus.GaugeVec
	WebhooksDelivered    prometheus.Counter
}

var (
	collectorOnce sync.Once
	collector     *Collector
)

// New returns the process-wide collector (safe to call from multiple tests).
func New() *Collector {
	collectorOnce.Do(func() {
		collector = &Collector{
			IncidentsProcessed: promauto.NewCounter(prometheus.CounterOpts{
				Name: "argus_incident_events_processed_total",
				Help: "Raw incidents and QA metric events processed",
			}),
			EscalationsPublished: promauto.NewCounter(prometheus.CounterOpts{
				Name: "argus_incident_escalations_published_total",
				Help: "Escalated incidents published to Kafka / webhooks",
			}),
			PolicyEvalSeconds: promauto.NewHistogram(prometheus.HistogramOpts{
				Name:    "argus_incident_policy_eval_seconds",
				Help:    "OPA policy evaluation latency",
				Buckets: prometheus.DefBuckets,
			}),
			BreakerState: promauto.NewGaugeVec(prometheus.GaugeOpts{
				Name: "argus_incident_breaker_state",
				Help: "Circuit breaker state per vehicle (0=closed,1=half_open,2=open)",
			}, []string{"vehicle_id"}),
			WebhooksDelivered: promauto.NewCounter(prometheus.CounterOpts{
				Name: "argus_incident_webhooks_delivered_total",
				Help: "Webhook deliveries attempted successfully",
			}),
		}
	})
	return collector
}

// Handler returns the Prometheus HTTP handler.
func Handler() http.Handler {
	return promhttp.Handler()
}

// SetBreaker maps state strings to numeric gauges.
func (c *Collector) SetBreaker(vehicleID, state string) {
	var v float64
	switch state {
	case "half_open":
		v = 1
	case "open":
		v = 2
	default:
		v = 0
	}
	c.BreakerState.WithLabelValues(vehicleID).Set(v)
}
