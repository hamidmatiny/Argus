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
		name       string
		advance    time.Duration
		shouldTrip bool
		wantState  State
		wantTrip   bool
	}{
		{name: "closed stays closed on success", shouldTrip: false, wantState: StateClosed, wantTrip: false},
		{name: "closed to open on trip", shouldTrip: true, wantState: StateOpen, wantTrip: true},
		{name: "open suppresses duplicate trip", shouldTrip: true, wantState: StateOpen, wantTrip: false},
		{name: "open to half-open after cooldown", advance: 11 * time.Second, shouldTrip: false, wantState: StateHalfOpen, wantTrip: false},
		{name: "half-open failure reopens", shouldTrip: true, wantState: StateOpen, wantTrip: true},
		{name: "open to half-open again", advance: 11 * time.Second, shouldTrip: false, wantState: StateHalfOpen, wantTrip: false},
		{name: "half-open success closes", shouldTrip: false, wantState: StateClosed, wantTrip: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			now = now.Add(tt.advance)
			b, tripped := s.Evaluate("VH-1", tt.shouldTrip, []string{"test"})
			if b.State != tt.wantState {
				t.Fatalf("state=%s want=%s", b.State, tt.wantState)
			}
			if tripped != tt.wantTrip {
				t.Fatalf("tripped=%v want=%v", tripped, tt.wantTrip)
			}
		})
	}
}

func TestPerVehicleIsolation(t *testing.T) {
	s := NewStore(Config{OpenCooldown: time.Minute, HalfOpenSuccessNeed: 1})
	b1, trip1 := s.Evaluate("VH-A", true, []string{"qa"})
	b2, trip2 := s.Evaluate("VH-B", false, nil)
	if !trip1 || b1.State != StateOpen {
		t.Fatalf("VH-A want open/tripped, got %+v trip=%v", b1, trip1)
	}
	if trip2 || b2.State != StateClosed {
		t.Fatalf("VH-B want closed, got %+v trip=%v", b2, trip2)
	}
}
