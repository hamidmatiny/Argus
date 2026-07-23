package auth_test

import (
	"testing"

	"github.com/argus-platform/argus/api-gateway/internal/auth"
)

func TestPrincipalRolePrecedence(t *testing.T) {
	p := auth.Principal{Roles: []string{"viewer", "operator"}}
	if p.Role() != "operator" {
		t.Fatalf("got %s", p.Role())
	}
	p = auth.Principal{Roles: []string{"admin", "viewer"}}
	if p.Role() != "admin" {
		t.Fatalf("got %s", p.Role())
	}
	p = auth.Principal{Roles: []string{"unknown"}}
	if p.Role() != "viewer" {
		t.Fatalf("default role got %s", p.Role())
	}
}

func TestParseAndValidateRejectsEmpty(t *testing.T) {
	v := &auth.Validator{}
	_, err := v.ParseAndValidate(nil, "")
	if err == nil {
		t.Fatal("expected error")
	}
}
