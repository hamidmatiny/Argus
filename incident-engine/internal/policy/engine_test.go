package policy

import (
	"context"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/argus-platform/argus/incident-engine/internal/models"
)

func policiesDir(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "..", "policies")
}

func TestRegoPolicies(t *testing.T) {
	ctx := context.Background()
	eng, err := Load(ctx, policiesDir(t))
	if err != nil {
		t.Fatalf("load: %v", err)
	}

	base := models.PolicyInput{
		VehicleID:             "VH-1",
		QAWindowBatches:       5,
		QABatchCount:          5,
		QARateThreshold:       0.15,
		DriftMinFeatures:      2,
		ConsecutiveFailureMax: 3,
		HourUTC:               10,
		Weekday:               6, // Saturday → slack
		BreakerState:          "closed",
	}

	t.Run("quarantine_rate_trips", func(t *testing.T) {
		in := base
		in.RollingQuarantineRate = 0.20
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if !dec.Trip {
			t.Fatalf("expected trip, got %+v", dec)
		}
		if !containsPrefix(dec.Reasons, "qa_quarantine_rate_exceeded") {
			t.Fatalf("reasons=%v", dec.Reasons)
		}
	})

	t.Run("quarantine_rate_needs_full_window", func(t *testing.T) {
		in := base
		in.QABatchCount = 2
		in.RollingQuarantineRate = 0.99
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if dec.Trip {
			t.Fatalf("expected no trip with partial window, got %+v", dec)
		}
	})

	t.Run("drift_count_trips", func(t *testing.T) {
		in := base
		in.DriftedFeatureCount = 2
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if !dec.Trip || !containsPrefix(dec.Reasons, "multi_feature_drift") {
			t.Fatalf("got %+v", dec)
		}
	})

	t.Run("consecutive_failures_trips", func(t *testing.T) {
		in := base
		in.ConsecutiveFailures = 3
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if !dec.Trip || !containsPrefix(dec.Reasons, "consecutive_qa_failures") {
			t.Fatalf("got %+v", dec)
		}
	})

	t.Run("business_hours_routes_pagerduty", func(t *testing.T) {
		in := base
		in.HourUTC = 15
		in.Weekday = 2 // Tuesday
		in.RollingQuarantineRate = 0.2
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if dec.Route != "pagerduty" {
			t.Fatalf("route=%s want pagerduty", dec.Route)
		}
		if dec.Severity != "critical" {
			t.Fatalf("severity=%s", dec.Severity)
		}
	})

	t.Run("business_hours_both_on_dual_signal", func(t *testing.T) {
		in := base
		in.HourUTC = 15
		in.Weekday = 2
		in.RollingQuarantineRate = 0.2
		in.DriftedFeatureCount = 3
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if dec.Route != "both" {
			t.Fatalf("route=%s want both", dec.Route)
		}
	})

	t.Run("off_hours_routes_slack", func(t *testing.T) {
		in := base
		in.HourUTC = 3
		in.Weekday = 2
		in.RollingQuarantineRate = 0.2
		dec, _, err := eng.Evaluate(ctx, in)
		if err != nil {
			t.Fatal(err)
		}
		if dec.Route != "slack" {
			t.Fatalf("route=%s want slack", dec.Route)
		}
	})
}

func containsPrefix(reasons []string, prefix string) bool {
	for _, r := range reasons {
		if len(r) >= len(prefix) && r[:len(prefix)] == prefix {
			return true
		}
	}
	return false
}
