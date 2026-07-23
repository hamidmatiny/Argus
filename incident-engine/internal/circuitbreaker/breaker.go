// Package circuitbreaker implements a per-vehicle CLOSED → OPEN → HALF_OPEN FSM.
package circuitbreaker

import (
	"sync"
	"time"
)

// State is the circuit breaker state.
type State string

const (
	StateClosed   State = "closed"
	StateOpen     State = "open"
	StateHalfOpen State = "half_open"
)

// Breaker is a single vehicle's circuit breaker.
type Breaker struct {
	VehicleID       string    `json:"vehicle_id"`
	State           State     `json:"state"`
	OpenedAt        time.Time `json:"opened_at,omitempty"`
	LastTransition  time.Time `json:"last_transition"`
	TripCount       int       `json:"trip_count"`
	HalfOpenSuccess int       `json:"half_open_success"`
	LastReasons     []string  `json:"last_reasons,omitempty"`
}

// Config tunes recovery behavior.
type Config struct {
	OpenCooldown        time.Duration
	HalfOpenSuccessNeed int
}

// Store holds per-vehicle breakers.
type Store struct {
	mu   sync.RWMutex
	cfg  Config
	byID map[string]*Breaker
	now  func() time.Time
}

// NewStore creates an empty breaker store.
func NewStore(cfg Config) *Store {
	if cfg.HalfOpenSuccessNeed < 1 {
		cfg.HalfOpenSuccessNeed = 1
	}
	if cfg.OpenCooldown <= 0 {
		cfg.OpenCooldown = 60 * time.Second
	}
	return &Store{
		cfg:  cfg,
		byID: make(map[string]*Breaker),
		now:  time.Now,
	}
}

// Get returns a copy of the breaker for vehicleID (creating closed if missing).
func (s *Store) Get(vehicleID string) Breaker {
	s.mu.Lock()
	defer s.mu.Unlock()
	b := s.getOrCreate(vehicleID)
	s.maybeAdvanceLocked(b)
	return *b
}

// Snapshot returns copies of all breakers.
func (s *Store) Snapshot() []Breaker {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Breaker, 0, len(s.byID))
	for _, b := range s.byID {
		s.maybeAdvanceLocked(b)
		cp := *b
		out = append(out, cp)
	}
	return out
}

// Evaluate applies a policy trip/success signal and returns the new state plus
// whether this call caused a fresh Closed→Open (or HalfOpen→Open) trip.
func (s *Store) Evaluate(vehicleID string, shouldTrip bool, reasons []string) (Breaker, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	b := s.getOrCreate(vehicleID)
	prev := b.State
	s.maybeAdvanceLocked(b)
	trippedNow := false
	now := s.now()

	// Cooldown only opens the probe window — do not count this call as success.
	if prev == StateOpen && b.State == StateHalfOpen {
		return *b, false
	}

	switch b.State {
	case StateClosed:
		if shouldTrip {
			b.State = StateOpen
			b.OpenedAt = now
			b.LastTransition = now
			b.TripCount++
			b.LastReasons = append([]string(nil), reasons...)
			b.HalfOpenSuccess = 0
			trippedNow = true
		}
	case StateOpen:
		// Suppress duplicate escalations while open; cooldown advances via maybeAdvance.
	case StateHalfOpen:
		if shouldTrip {
			b.State = StateOpen
			b.OpenedAt = now
			b.LastTransition = now
			b.TripCount++
			b.LastReasons = append([]string(nil), reasons...)
			b.HalfOpenSuccess = 0
			trippedNow = true
		} else {
			b.HalfOpenSuccess++
			if b.HalfOpenSuccess >= s.cfg.HalfOpenSuccessNeed {
				b.State = StateClosed
				b.LastTransition = now
				b.HalfOpenSuccess = 0
				b.LastReasons = nil
			}
		}
	}
	return *b, trippedNow
}

func (s *Store) getOrCreate(vehicleID string) *Breaker {
	if b, ok := s.byID[vehicleID]; ok {
		return b
	}
	b := &Breaker{
		VehicleID:      vehicleID,
		State:          StateClosed,
		LastTransition: s.now(),
	}
	s.byID[vehicleID] = b
	return b
}

// maybeAdvanceLocked moves OPEN → HALF_OPEN after the cooldown.
func (s *Store) maybeAdvanceLocked(b *Breaker) {
	if b.State != StateOpen {
		return
	}
	if s.now().Sub(b.OpenedAt) >= s.cfg.OpenCooldown {
		b.State = StateHalfOpen
		b.LastTransition = s.now()
		b.HalfOpenSuccess = 0
	}
}
