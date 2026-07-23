package circuitbreaker

import (
	"testing"
	"time"
)

func TestStateMachineTransitions(t *testing.T) {
	fixed := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	now := fixed

	s := NewStore(Config{OpenCooldown: 10 * time.Second, HalfOpenSuccessNeed: 1})
	s.now = func() time.Time { return now }

	tests := []struct {
		name          string
		advance       time.Duration
		shouldTrip    bool
		wantState     State
		wantTrip      bool
		wantRecovered bool
	}{
		{name: "closed stays closed on success", shouldTrip: false, wantState: StateClosed},
		{name: "closed to open on trip", shouldTrip: true, wantState: StateOpen, wantTrip: true},
		{name: "open suppresses duplicate trip", shouldTrip: true, wantState: StateOpen},
		{name: "open to half-open after cooldown", advance: 11 * time.Second, shouldTrip: false, wantState: StateHalfOpen},
		{name: "half-open failure reopens", shouldTrip: true, wantState: StateOpen, wantTrip: true},
		{name: "open to half-open again", advance: 11 * time.Second, shouldTrip: false, wantState: StateHalfOpen},
		{name: "half-open success closes", shouldTrip: false, wantState: StateClosed, wantRecovered: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			now = now.Add(tt.advance)
			out := s.Evaluate("VH-1", tt.shouldTrip, []string{"test"})
			if out.Breaker.State != tt.wantState {
				t.Fatalf("state=%s want=%s", out.Breaker.State, tt.wantState)
			}
			if out.Tripped != tt.wantTrip {
				t.Fatalf("tripped=%v want=%v", out.Tripped, tt.wantTrip)
			}
			if out.Recovered != tt.wantRecovered {
				t.Fatalf("recovered=%v want=%v", out.Recovered, tt.wantRecovered)
			}
		})
	}
}

func TestPerVehicleIsolation(t *testing.T) {
	s := NewStore(Config{OpenCooldown: time.Minute, HalfOpenSuccessNeed: 1})
	a := s.Evaluate("VH-A", true, []string{"qa"})
	b := s.Evaluate("VH-B", false, nil)
	if !a.Tripped || a.Breaker.State != StateOpen {
		t.Fatalf("VH-A want open/tripped, got %+v", a)
	}
	if b.Tripped || b.Breaker.State != StateClosed {
		t.Fatalf("VH-B want closed, got %+v", b)
	}
}
