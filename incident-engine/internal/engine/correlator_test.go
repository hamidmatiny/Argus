package engine

import (
	"context"
	"encoding/json"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/segmentio/kafka-go"

	"github.com/argus-platform/argus/incident-engine/internal/circuitbreaker"
	"github.com/argus-platform/argus/incident-engine/internal/config"
	"github.com/argus-platform/argus/incident-engine/internal/metrics"
	"github.com/argus-platform/argus/incident-engine/internal/models"
	"github.com/argus-platform/argus/incident-engine/internal/policy"
	"github.com/argus-platform/argus/incident-engine/internal/webhook"
)

func testPolicies(t *testing.T) *policy.Engine {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("caller")
	}
	dir := filepath.Join(filepath.Dir(file), "..", "..", "policies")
	eng, err := policy.Load(context.Background(), dir)
	if err != nil {
		t.Fatalf("policy load: %v", err)
	}
	return eng
}

func newTestCorrelator(t *testing.T, cooldown time.Duration) (*Correlator, *circuitbreaker.Store) {
	t.Helper()
	cfg := config.Config{
		QAWindowBatches:     5,
		QARateThreshold:     0.15,
		DriftMinFeatures:    2,
		ConsecutiveFailMax:  3,
		SlackChannel:        "#test",
		PagerDutyRoutingKey: "test",
	}
	store := circuitbreaker.NewStore(circuitbreaker.Config{
		OpenCooldown:        cooldown,
		HalfOpenSuccessNeed: 1,
	})
	corr := NewCorrelator(cfg, testPolicies(t), store, nil, webhook.NewDispatcher("", "", ""), metrics.New())
	return corr, store
}

func qaMsg(vehicle string, rate float64, exceeded bool) kafka.Message {
	body, _ := json.Marshal(models.QaMetricEvent{
		VehicleID:      vehicle,
		WindowSize:     20,
		Total:          20,
		Quarantined:    int(rate * 20),
		QuarantineRate: rate,
		Threshold:      0.15,
		Exceeded:       exceeded,
		WindowEnd:      time.Now().UTC(),
		Type:           "qa_quarantine_rate",
	})
	return kafka.Message{Value: body}
}

func TestIncidentAutoResolvesOnBreakerRecovery(t *testing.T) {
	ctx := context.Background()
	corr, store := newTestCorrelator(t, 10*time.Second)
	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	store.SetNow(func() time.Time { return now })

	// Fill 5-batch window above quarantine threshold → trip.
	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg("VH-0000042", 0.25, true)); err != nil {
			t.Fatal(err)
		}
	}
	open := corr.ListIncidents("open")
	if len(open) != 1 {
		t.Fatalf("want 1 open incident, got %d", len(open))
	}
	if open[0].VehicleID != "VH-0000042" {
		t.Fatalf("vehicle=%s", open[0].VehicleID)
	}
	id := open[0].IncidentID

	// Dilute the rolling window while open so recovery probes are not re-trips.
	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg("VH-0000042", 0.01, false)); err != nil {
			t.Fatal(err)
		}
	}
	// Advance past cooldown → half-open, then healthy QA → closed + auto-resolve.
	now = now.Add(11 * time.Second)
	if err := corr.HandleQA(ctx, qaMsg("VH-0000042", 0.01, false)); err != nil {
		t.Fatal(err) // enters half-open (no probe success yet)
	}
	if err := corr.HandleQA(ctx, qaMsg("VH-0000042", 0.01, false)); err != nil {
		t.Fatal(err) // probe success → closed
	}

	if got := corr.ListIncidents("open"); len(got) != 0 {
		t.Fatalf("want 0 open, got %+v", got)
	}
	resolved := corr.ListIncidents("resolved")
	if len(resolved) != 1 || resolved[0].IncidentID != id {
		t.Fatalf("resolved=%+v", resolved)
	}
	if resolved[0].ResolvedAt == "" || resolved[0].ResolveReason != "breaker_recovered" {
		t.Fatalf("bad resolve fields: %+v", resolved[0])
	}
	if store.Get("VH-0000042").State != circuitbreaker.StateClosed {
		t.Fatalf("breaker state=%s", store.Get("VH-0000042").State)
	}
}

func TestRetripKeepsSingleIncidentID(t *testing.T) {
	ctx := context.Background()
	corr, store := newTestCorrelator(t, 10*time.Second)
	now := time.Date(2026, 7, 23, 14, 0, 0, 0, time.UTC)
	store.SetNow(func() time.Time { return now })
	vehicle := "VH-0000077"

	// Closed → Open (fresh episode).
	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.30, true)); err != nil {
			t.Fatal(err)
		}
	}
	open := corr.ListIncidents("open")
	if len(open) != 1 {
		t.Fatalf("after first trip want 1 open, got %d", len(open))
	}
	firstID := open[0].IncidentID
	firstTS := open[0].Timestamp
	if open[0].RetripCount != 0 {
		t.Fatalf("fresh trip retrip_count=%d want 0", open[0].RetripCount)
	}

	// Stay unhealthy; after cooldown the next evaluation advances Open→HalfOpen
	// (via Get) then HalfOpen→Open on the same call (retrip).
	now = now.Add(11 * time.Second)
	if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.35, true)); err != nil {
		t.Fatal(err)
	}

	open = corr.ListIncidents("open")
	if len(open) != 1 {
		t.Fatalf("after retrip want exactly 1 open incident, got %d: %+v", len(open), open)
	}
	if open[0].IncidentID != firstID {
		t.Fatalf("incident_id changed on retrip: %s → %s", firstID, open[0].IncidentID)
	}
	if open[0].Timestamp != firstTS {
		t.Fatalf("timestamp mutated: %s → %s", firstTS, open[0].Timestamp)
	}
	if open[0].RetripCount < 1 {
		t.Fatalf("retrip_count=%d want >=1", open[0].RetripCount)
	}
	if open[0].LastUpdatedAt == "" || open[0].LastUpdatedAt == firstTS {
		// LastUpdatedAt may equal firstTS only if clock frozen at same ns; with
		// frozen test clock Refresh uses time.Now() wall clock so it should differ.
		if open[0].LastUpdatedAt == "" {
			t.Fatal("last_updated_at empty after retrip")
		}
	}
	if len(open[0].Reasons) == 0 {
		t.Fatal("reasons empty after retrip")
	}

	// Genuine recovery: dilute window, half-open, then close.
	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.01, false)); err != nil {
			t.Fatal(err)
		}
	}
	now = now.Add(11 * time.Second)
	if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.01, false)); err != nil {
		t.Fatal(err)
	}
	if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.01, false)); err != nil {
		t.Fatal(err)
	}
	if len(corr.ListIncidents("open")) != 0 {
		t.Fatalf("want resolved, still open: %+v", corr.ListIncidents("open"))
	}
	resolved := corr.ListIncidents("resolved")
	if len(resolved) != 1 || resolved[0].IncidentID != firstID {
		t.Fatalf("resolved=%+v", resolved)
	}

	// Subsequent fresh trip after resolution → new incident_id.
	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg(vehicle, 0.40, true)); err != nil {
			t.Fatal(err)
		}
	}
	open = corr.ListIncidents("open")
	if len(open) != 1 {
		t.Fatalf("second episode want 1 open, got %d", len(open))
	}
	if open[0].IncidentID == firstID {
		t.Fatalf("expected new incident_id after resolution, got same %s", firstID)
	}
	if open[0].RetripCount != 0 {
		t.Fatalf("new episode retrip_count=%d want 0", open[0].RetripCount)
	}
}

func TestManualResolveIdempotent(t *testing.T) {
	ctx := context.Background()
	corr, _ := newTestCorrelator(t, time.Minute)

	for i := 0; i < 5; i++ {
		if err := corr.HandleQA(ctx, qaMsg("VH-0000099", 0.30, true)); err != nil {
			t.Fatal(err)
		}
	}
	open := corr.ListIncidents("open")
	if len(open) != 1 {
		t.Fatalf("want 1 open, got %d", len(open))
	}
	id := open[0].IncidentID

	first, err := corr.ResolveIncident(id)
	if err != nil {
		t.Fatal(err)
	}
	if first.Open || first.Status != "resolved" || first.ResolveReason != "manual" {
		t.Fatalf("first=%+v", first)
	}
	resolvedAt := first.ResolvedAt

	second, err := corr.ResolveIncident(id)
	if err != nil {
		t.Fatal(err)
	}
	if second.ResolvedAt != resolvedAt || second.Status != "resolved" {
		t.Fatalf("idempotent mismatch first=%+v second=%+v", first, second)
	}
	if len(corr.ListIncidents("open")) != 0 {
		t.Fatal("still open after resolve")
	}
}
