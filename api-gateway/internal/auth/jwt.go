package auth

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/MicahParks/keyfunc/v3"
	"github.com/golang-jwt/jwt/v5"
)

// Principal is the authenticated caller.
type Principal struct {
	Subject string
	Email   string
	Roles   []string
	APIKey  string
}

type ctxKey struct{}

// WithPrincipal stores the principal on the context.
func WithPrincipal(ctx context.Context, p Principal) context.Context {
	return context.WithValue(ctx, ctxKey{}, p)
}

// FromContext returns the principal if present.
func FromContext(ctx context.Context) (Principal, bool) {
	p, ok := ctx.Value(ctxKey{}).(Principal)
	return p, ok
}

// Role returns the highest Argus role from the principal.
func (p Principal) Role() string {
	rank := map[string]int{"viewer": 1, "operator": 2, "admin": 3}
	best := "viewer"
	bestN := 0
	for _, r := range p.Roles {
		r = strings.ToLower(strings.TrimSpace(r))
		if n, ok := rank[r]; ok && n > bestN {
			best = r
			bestN = n
		}
	}
	return best
}

// Validator validates OIDC JWTs against a JWKS endpoint.
type Validator struct {
	issuer   string
	audience string
	jwks     keyfunc.Keyfunc
}

// NewValidator constructs a JWKS-backed JWT validator.
func NewValidator(ctx context.Context, issuer, audience, jwksURL string) (*Validator, error) {
	if jwksURL == "" && issuer != "" {
		jwksURL = strings.TrimRight(issuer, "/") + "/protocol/openid-connect/certs"
	}
	k, err := keyfunc.NewDefaultCtx(ctx, []string{jwksURL})
	if err != nil {
		return nil, fmt.Errorf("jwks: %w", err)
	}
	return &Validator{issuer: issuer, audience: audience, jwks: k}, nil
}

// NewValidatorWithKeyfunc is used by tests with a prebuilt keyfunc.
func NewValidatorWithKeyfunc(issuer, audience string, k keyfunc.Keyfunc) *Validator {
	return &Validator{issuer: issuer, audience: audience, jwks: k}
}

// ParseAndValidate verifies the bearer token and returns a principal.
func (v *Validator) ParseAndValidate(_ context.Context, raw string) (Principal, error) {
	if raw == "" {
		return Principal{}, fmt.Errorf("missing token")
	}
	if v == nil || v.jwks == nil {
		return Principal{}, fmt.Errorf("validator not configured")
	}
	token, err := jwt.Parse(raw, v.jwks.Keyfunc,
		jwt.WithExpirationRequired(),
		jwt.WithLeeway(30*time.Second),
	)
	if err != nil {
		return Principal{}, err
	}
	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok || !token.Valid {
		return Principal{}, fmt.Errorf("invalid token claims")
	}
	if v.issuer != "" {
		iss, _ := claims["iss"].(string)
		if iss != v.issuer {
			return Principal{}, fmt.Errorf("issuer mismatch")
		}
	}
	if v.audience != "" && !audienceOK(claims, v.audience) {
		return Principal{}, fmt.Errorf("audience mismatch")
	}
	sub, _ := claims["sub"].(string)
	email, _ := claims["email"].(string)
	return Principal{
		Subject: sub,
		Email:   email,
		Roles:   extractRoles(claims),
	}, nil
}

func audienceOK(claims jwt.MapClaims, want string) bool {
	switch a := claims["aud"].(type) {
	case string:
		if a == want {
			return true
		}
	case []any:
		for _, v := range a {
			if s, ok := v.(string); ok && s == want {
				return true
			}
		}
	}
	if azp, _ := claims["azp"].(string); azp == want {
		return true
	}
	return false
}

func extractRoles(claims jwt.MapClaims) []string {
	var roles []string
	if realm, ok := claims["realm_access"].(map[string]any); ok {
		if arr, ok := realm["roles"].([]any); ok {
			for _, r := range arr {
				if s, ok := r.(string); ok {
					roles = append(roles, s)
				}
			}
		}
	}
	if res, ok := claims["resource_access"].(map[string]any); ok {
		for _, v := range res {
			m, ok := v.(map[string]any)
			if !ok {
				continue
			}
			arr, _ := m["roles"].([]any)
			for _, r := range arr {
				if s, ok := r.(string); ok {
					roles = append(roles, s)
				}
			}
		}
	}
	if arr, ok := claims["roles"].([]any); ok {
		for _, r := range arr {
			if s, ok := r.(string); ok {
				roles = append(roles, s)
			}
		}
	}
	return roles
}
