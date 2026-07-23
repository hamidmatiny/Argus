package ratelimit_test

import (
	"testing"

	"github.com/argus-platform/argus/api-gateway/internal/ratelimit"
)

func TestTokenBucket(t *testing.T) {
	l := ratelimit.New(10, 2)
	if !l.Allow("a") || !l.Allow("a") {
		t.Fatal("expected burst of 2")
	}
	if l.Allow("a") {
		t.Fatal("expected deny after burst")
	}
	if !l.Allow("b") {
		t.Fatal("other key should have its own bucket")
	}
}
