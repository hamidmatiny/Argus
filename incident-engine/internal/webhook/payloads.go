package webhook

import (
	"fmt"
	"strings"

	"github.com/argus-platform/argus/incident-engine/internal/models"
)

// BuildChannels creates Slack- and PagerDuty-shaped notification payloads
// (sentinel-ray / vanguard-style structured on-call report).
func BuildChannels(
	esc models.EscalatedIncident,
	slackChannel, pdRoutingKey string,
) map[string]any {
	summary := esc.Summary
	if summary == "" {
		summary = fmt.Sprintf("ARGUS circuit breaker tripped for %s", esc.VehicleID)
	}
	slackText := fmt.Sprintf(
		":rotating_light: *ARGUS Incident* | vehicle `%s` | %s | reasons=%s",
		esc.VehicleID,
		esc.Severity,
		strings.Join(esc.Reasons, "; "),
	)
	if esc.RetripCount > 0 {
		slackText = fmt.Sprintf(
			"[UPDATED x%d] :rotating_light: *ARGUS Incident* (ongoing) | vehicle `%s` | %s | reasons=%s | id=`%s`",
			esc.RetripCount,
			esc.VehicleID,
			esc.Severity,
			strings.Join(esc.Reasons, "; "),
			esc.IncidentID,
		)
		summary = fmt.Sprintf("[UPDATED x%d] %s", esc.RetripCount, summary)
	}
	return map[string]any{
		"slack": map[string]any{
			"channel": slackChannel,
			"text":    slackText,
		},
		"pagerduty": map[string]any{
			"routing_key":  pdRoutingKey,
			"event_action": "trigger",
			"dedup_key":    esc.IncidentID,
			"payload": map[string]any{
				"summary":   summary,
				"severity":  mapSeverity(esc.Severity),
				"source":    "argus-incident-engine",
				"component": esc.VehicleID,
				"custom_details": map[string]any{
					"vehicle_id":      esc.VehicleID,
					"incident_id":     esc.IncidentID,
					"reasons":         esc.Reasons,
					"route":           esc.Route,
					"metrics":         esc.Metrics,
					"retrip_count":    esc.RetripCount,
					"last_updated_at": esc.LastUpdatedAt,
				},
			},
		},
	}
}

func mapSeverity(s string) string {
	switch strings.ToLower(s) {
	case "critical":
		return "critical"
	case "warning":
		return "warning"
	case "info":
		return "info"
	default:
		return "error"
	}
}
