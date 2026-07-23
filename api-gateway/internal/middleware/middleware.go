package middleware

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/argus-platform/argus/api-gateway/internal/auth"
	"github.com/argus-platform/argus/api-gateway/internal/authz"
	"github.com/argus-platform/argus/api-gateway/internal/ratelimit"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	httpRequests = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "argus_gateway_http_requests_total",
		Help: "HTTP requests handled by api-gateway",
	}, []string{"path", "code", "role"})
	httpDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "argus_gateway_http_duration_seconds",
		Help:    "HTTP request latency",
		Buckets: prometheus.DefBuckets,
	}, []string{"path"})
	authRejections = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "argus_gateway_auth_rejections_total",
		Help: "AuthN/AuthZ rejections",
	}, []string{"reason"})
	rateLimited = promauto.NewCounter(prometheus.CounterOpts{
		Name: "argus_gateway_rate_limited_total",
		Help: "Requests rejected by rate limiter",
	})
)

// Deps wires cross-cutting HTTP middleware.
type Deps struct {
	AuthDisabled bool
	Validator    *auth.Validator
	OPA          *authz.Engine
	Limiter      *ratelimit.Limiter
	APIKeys      map[string]string
}

// Chain applies logging, metrics, rate-limit, authn, authz.
func Chain(next http.Handler, d Deps) http.Handler {
	h := next
	h = withAuthz(h, d)
	h = withAuthn(h, d)
	h = withRateLimit(h, d)
	h = withMetrics(h)
	h = withLogging(h)
	return h
}

func publicPath(path string) bool {
	switch path {
	case "/health", "/healthz", "/readyz", "/metrics", "/openapi.json", "/v1/ping":
		return true
	default:
		return false
	}
}

func withLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := &statusWriter{ResponseWriter: w, code: 200}
		next.ServeHTTP(ww, r)
		slog.Info("http_request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", ww.code,
			"duration_ms", time.Since(start).Milliseconds(),
			"traceparent", r.Header.Get("traceparent"),
		)
	})
}

func withMetrics(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := &statusWriter{ResponseWriter: w, code: 200}
		next.ServeHTTP(ww, r)
		role := "anonymous"
		if p, ok := auth.FromContext(r.Context()); ok {
			role = p.Role()
		}
		path := normalizePath(r.URL.Path)
		httpRequests.WithLabelValues(path, http.StatusText(ww.code), role).Inc()
		httpDuration.WithLabelValues(path).Observe(time.Since(start).Seconds())
	})
}

func withRateLimit(next http.Handler, d Deps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if publicPath(r.URL.Path) || d.Limiter == nil {
			next.ServeHTTP(w, r)
			return
		}
		key := r.Header.Get("X-API-Key")
		if key == "" {
			key = strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
			if len(key) > 24 {
				key = key[:24]
			}
		}
		if key == "" {
			key = r.RemoteAddr
		}
		if !d.Limiter.Allow(key) {
			rateLimited.Inc()
			writeErr(w, http.StatusTooManyRequests, "rate limit exceeded")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func withAuthn(next http.Handler, d Deps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if publicPath(r.URL.Path) {
			next.ServeHTTP(w, r)
			return
		}
		if d.AuthDisabled {
			role := r.Header.Get("X-Argus-Role")
			if role == "" {
				role = "admin"
			}
			p := auth.Principal{Subject: "dev", Roles: []string{role}}
			if k := r.Header.Get("X-API-Key"); k != "" {
				p.APIKey = k
				if mapped, ok := d.APIKeys[k]; ok {
					p.Roles = []string{mapped}
				}
			}
			next.ServeHTTP(w, r.WithContext(auth.WithPrincipal(r.Context(), p)))
			return
		}

		if k := r.Header.Get("X-API-Key"); k != "" {
			if role, ok := d.APIKeys[k]; ok {
				p := auth.Principal{Subject: "api-key:" + k, APIKey: k, Roles: []string{role}}
				next.ServeHTTP(w, r.WithContext(auth.WithPrincipal(r.Context(), p)))
				return
			}
			authRejections.WithLabelValues("bad_api_key").Inc()
			writeErr(w, http.StatusUnauthorized, "invalid api key")
			return
		}

		h := r.Header.Get("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			authRejections.WithLabelValues("missing_bearer").Inc()
			writeErr(w, http.StatusUnauthorized, "missing bearer token")
			return
		}
		raw := strings.TrimPrefix(h, "Bearer ")
		if d.Validator == nil {
			authRejections.WithLabelValues("validator_unconfigured").Inc()
			writeErr(w, http.StatusServiceUnavailable, "auth not ready")
			return
		}
		p, err := d.Validator.ParseAndValidate(r.Context(), raw)
		if err != nil {
			authRejections.WithLabelValues("invalid_jwt").Inc()
			writeErr(w, http.StatusUnauthorized, "invalid token")
			return
		}
		next.ServeHTTP(w, r.WithContext(auth.WithPrincipal(r.Context(), p)))
	})
}

func withAuthz(next http.Handler, d Deps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if publicPath(r.URL.Path) || d.OPA == nil {
			next.ServeHTTP(w, r)
			return
		}
		p, ok := auth.FromContext(r.Context())
		if !ok {
			authRejections.WithLabelValues("no_principal").Inc()
			writeErr(w, http.StatusUnauthorized, "unauthorized")
			return
		}
		allowed, err := d.OPA.Allow(r.Context(), authz.Input{
			Role:   p.Role(),
			Method: r.Method,
			Path:   r.URL.Path,
		})
		if err != nil {
			writeErr(w, http.StatusInternalServerError, "authz error")
			return
		}
		if !allowed {
			authRejections.WithLabelValues("opa_deny").Inc()
			writeErr(w, http.StatusForbidden, "forbidden")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func normalizePath(p string) string {
	if strings.HasPrefix(p, "/v1/incidents/") && strings.HasSuffix(p, "/acknowledge") {
		return "/v1/incidents/{id}/acknowledge"
	}
	return p
}

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (w *statusWriter) WriteHeader(code int) {
	w.code = code
	w.ResponseWriter.WriteHeader(code)
}

func writeErr(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]any{"error": msg})
}
