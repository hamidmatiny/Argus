// Command api-gateway is a Phase-8 stub: health, Prometheus metrics, and OTel traces.
// Full authz (OPA) lands in a later phase; this service exists so observability can
// scrape/trace a north-south edge today.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

var (
	httpRequests = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "argus_gateway_http_requests_total",
		Help: "HTTP requests handled by the api-gateway stub",
	}, []string{"path", "code"})
	httpDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "argus_gateway_http_duration_seconds",
		Help:    "HTTP request latency",
		Buckets: prometheus.DefBuckets,
	}, []string{"path"})
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))
	addr := getenv("API_GATEWAY_ADDR", ":8099")

	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck(addr))
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	tp, err := initTracer(ctx)
	if err != nil {
		slog.Warn("otel_init_failed", "err", err)
	} else if tp != nil {
		defer func() { _ = tp.Shutdown(context.Background()) }()
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/healthz", handleHealth)
	mux.HandleFunc("/readyz", handleHealth)
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/v1/ping", handlePing)
	mux.HandleFunc("/", handleRoot)

	handler := otelhttp.NewHandler(withMetrics(mux), "api-gateway")
	srv := &http.Server{Addr: addr, Handler: handler, ReadHeaderTimeout: 5 * time.Second}

	go func() {
		slog.Info("http_listen", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("http_failed", "err", err)
			stop()
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}

func initTracer(ctx context.Context) (*sdktrace.TracerProvider, error) {
	endpoint := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if endpoint == "" {
		return nil, nil
	}
	exp, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpointURL(normalizeTracesURL(endpoint)),
	)
	if err != nil {
		return nil, err
	}
	// Avoid resource.Merge(Default(), ...) — Default() and semconv can disagree on SchemaURL.
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName("api-gateway"),
			semconv.ServiceNamespace("argus"),
		),
	)
	if err != nil {
		return nil, err
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	slog.Info("otel_enabled", "endpoint", endpoint)
	return tp, nil
}

func normalizeTracesURL(endpoint string) string {
	// Accept host:port or full URL; otlptracehttp WithEndpointURL wants a full URL.
	if len(endpoint) >= 4 && (endpoint[:4] == "http") {
		if len(endpoint) < 12 || endpoint[len(endpoint)-11:] != "/v1/traces" {
			return endpoint + "/v1/traces"
		}
		return endpoint
	}
	return "http://" + endpoint + "/v1/traces"
}

func withMetrics(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := &statusWriter{ResponseWriter: w, code: 200}
		next.ServeHTTP(ww, r)
		path := r.URL.Path
		httpRequests.WithLabelValues(path, http.StatusText(ww.code)).Inc()
		httpDuration.WithLabelValues(path).Observe(time.Since(start).Seconds())
	})
}

type statusWriter struct {
	http.ResponseWriter
	code int
}

func (w *statusWriter) WriteHeader(code int) {
	w.code = code
	w.ResponseWriter.WriteHeader(code)
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "api-gateway", "ready": true})
}

func handlePing(w http.ResponseWriter, r *http.Request) {
	_, span := otel.Tracer("api-gateway").Start(r.Context(), "ping")
	defer span.End()
	span.SetAttributes(attribute.String("argus.route", "/v1/ping"))
	writeJSON(w, http.StatusOK, map[string]any{"pong": true, "ts": time.Now().UTC().Format(time.RFC3339Nano)})
}

func handleRoot(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"service": "api-gateway",
		"phase":   "stub",
		"routes":  []string{"/health", "/metrics", "/v1/ping"},
	})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func runHealthcheck(addr string) int {
	host := addr
	if len(host) > 0 && host[0] == ':' {
		host = "127.0.0.1" + host
	}
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://" + host + "/healthz")
	if err != nil {
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 1
	}
	return 0
}
