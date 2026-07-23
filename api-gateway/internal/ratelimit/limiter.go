package ratelimit

import (
	"sync"
	"time"
)

// Limiter is a per-key token bucket.
type Limiter struct {
	rps   float64
	burst float64
	mu    sync.Mutex
	buckets map[string]*bucket
}

type bucket struct {
	tokens float64
	last   time.Time
}

// New creates a limiter with the given refill rate and burst size.
func New(rps float64, burst int) *Limiter {
	if rps <= 0 {
		rps = 10
	}
	if burst <= 0 {
		burst = int(rps)
	}
	return &Limiter{
		rps:     rps,
		burst:   float64(burst),
		buckets: map[string]*bucket{},
	}
}

// Allow reports whether key may proceed and consumes one token when true.
func (l *Limiter) Allow(key string) bool {
	if key == "" {
		key = "anonymous"
	}
	now := time.Now()
	l.mu.Lock()
	defer l.mu.Unlock()
	b, ok := l.buckets[key]
	if !ok {
		l.buckets[key] = &bucket{tokens: l.burst - 1, last: now}
		return true
	}
	elapsed := now.Sub(b.last).Seconds()
	b.tokens += elapsed * l.rps
	if b.tokens > l.burst {
		b.tokens = l.burst
	}
	b.last = now
	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}
