package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/argus-platform/argus/api-gateway/internal/auth"
	"github.com/argus-platform/argus/api-gateway/internal/authz"
	"github.com/argus-platform/argus/api-gateway/internal/config"
	"github.com/argus-platform/argus/api-gateway/internal/server"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))
	cfg := config.Load()

	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck(cfg.HTTPAddr))
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	tp, err := initTracer(ctx, cfg.OTELEndpoint)
	if err != nil {
		slog.Warn("otel_init_failed", "err", err)
	} else if tp != nil {
		defer func() { _ = tp.Shutdown(context.Background()) }()
	}

	policyDir := cfg.PolicyDir
	if !filepath.IsAbs(policyDir) {
		if _, err := os.Stat(policyDir); err != nil {
			if _, err2 := os.Stat("/etc/argus/policies"); err2 == nil {
				policyDir = "/etc/argus/policies"
			}
		}
	}
	opa, err := authz.Load(ctx, policyDir)
	if err != nil {
		slog.Error("policy_load_failed", "err", err, "dir", policyDir)
		os.Exit(1)
	}

	var validator *auth.Validator
	if !cfg.AuthDisabled {
		v, err := auth.NewValidator(ctx, cfg.OIDCIssuer, cfg.OIDCAudience, cfg.JWKSURL)
		if err != nil {
			slog.Warn("oidc_validator_init_failed", "err", err, "hint", "set API_GATEWAY_AUTH_DISABLED=true for local no-auth")
		} else {
			validator = v
			slog.Info("oidc_enabled", "issuer", cfg.OIDCIssuer, "audience", cfg.OIDCAudience)
		}
	} else {
		slog.Warn("auth_disabled", "mode", "dev")
	}

	openapiPath := getenv("API_GATEWAY_OPENAPI_PATH", "openapi/gateway.swagger.json")
	if _, err := os.Stat(openapiPath); err != nil {
		if _, err2 := os.Stat("/etc/argus/openapi/gateway.swagger.json"); err2 == nil {
			openapiPath = "/etc/argus/openapi/gateway.swagger.json"
		}
	}

	app := &server.App{
		CFG:       cfg,
		Gateway:   server.NewGatewayFromConfig(cfg),
		OPA:       opa,
		Validator: validator,
		OpenAPI:   server.LoadOpenAPI(openapiPath),
	}

	slog.Info("api_gateway_starting",
		"http", cfg.HTTPAddr,
		"grpc", cfg.GRPCAddr,
		"auth_disabled", cfg.AuthDisabled,
	)
	if err := app.ListenAndServe(ctx); err != nil {
		slog.Error("server_failed", "err", err)
		os.Exit(1)
	}
}

func initTracer(ctx context.Context, endpoint string) (*sdktrace.TracerProvider, error) {
	if endpoint == "" {
		return nil, nil
	}
	exp, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(normalizeTracesURL(endpoint)))
	if err != nil {
		return nil, err
	}
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
	if len(endpoint) >= 4 && endpoint[:4] == "http" {
		if len(endpoint) < 12 || endpoint[len(endpoint)-11:] != "/v1/traces" {
			return endpoint + "/v1/traces"
		}
		return endpoint
	}
	return "http://" + endpoint + "/v1/traces"
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

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
