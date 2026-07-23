# Aggregate trip + escalation routing (business hours → PagerDuty).
package argus.incident

default trip = false
default route = "slack"
default severity = "warning"

trip {
	trip_quarantine
}

trip {
	trip_drift
}

trip {
	trip_consecutive
}

business_hours {
	input.weekday >= 1
	input.weekday <= 5
	input.hour_utc >= 13
	input.hour_utc < 21
}

dual_signal {
	input.drifted_feature_count >= input.drift_min_features
	input.rolling_quarantine_rate > input.qa_rate_threshold
}

route = "pagerduty" {
	business_hours
	not dual_signal
}

route = "both" {
	business_hours
	dual_signal
}

severity = "critical" {
	trip
}

reasons[reason_quarantine] {
	trip_quarantine
}

reasons[reason_drift] {
	trip_drift
}

reasons[reason_consecutive] {
	trip_consecutive
}
