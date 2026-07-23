package server

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/argus-platform/argus/api-gateway/internal/auth"
	"github.com/argus-platform/argus/api-gateway/internal/authz"
	"github.com/argus-platform/argus/api-gateway/internal/config"
	"github.com/argus-platform/argus/api-gateway/internal/middleware"
	"github.com/argus-platform/argus/api-gateway/internal/ratelimit"
	"github.com/argus-platform/argus/api-gateway/internal/service"
	"github.com/argus-platform/argus/api-gateway/internal/upstream"
	argusv1 "github.com/argus-platform/argus/shared/gen/go/argus/v1"
	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/reflection"
	"google.golang.org/protobuf/encoding/protojson"
)

// App owns HTTP + gRPC listeners.
type App struct {
	CFG      config.Config
	Gateway  *service.Gateway
	OPA      *authz.Engine
	Validator *auth.Validator
	OpenAPI  []byte
}

// ListenAndServe starts gRPC and HTTP (grpc-gateway) servers.
func (a *App) ListenAndServe(ctx context.Context) error {
	grpcServer := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
	)
	argusv1.RegisterGatewayServiceServer(grpcServer, a.Gateway)
	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", a.CFG.GRPCAddr)
	if err != nil {
		return err
	}
	go func() {
		_ = grpcServer.Serve(lis)
	}()
	go func() {
		<-ctx.Done()
		grpcServer.GracefulStop()
	}()

	gwmux := runtime.NewServeMux(
		runtime.WithMarshalerOption(runtime.MIMEWildcard, &runtime.JSONPb{
			MarshalOptions: protojson.MarshalOptions{
				UseProtoNames:   true,
				EmitUnpopulated: false,
			},
			UnmarshalOptions: protojson.UnmarshalOptions{
				DiscardUnknown: true,
			},
		}),
	)
	// In-process registration avoids a loopback dial for REST.
	if err := argusv1.RegisterGatewayServiceHandlerServer(ctx, gwmux, a.Gateway); err != nil {
		// Fall back to dialing local gRPC if HandlerServer is unavailable for streaming.
		opts := []grpc.DialOption{
			grpc.WithTransportCredentials(insecure.NewCredentials()),
			grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		}
		if err := argusv1.RegisterGatewayServiceHandlerFromEndpoint(ctx, gwmux, a.CFG.GRPCAddr, opts); err != nil {
			return err
		}
	}

	root := http.NewServeMux()
	root.HandleFunc("/health", handleHealth)
	root.HandleFunc("/healthz", handleHealth)
	root.HandleFunc("/readyz", handleHealth)
	root.Handle("/metrics", promhttp.Handler())
	root.HandleFunc("/openapi.json", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if len(a.OpenAPI) == 0 {
			_ = json.NewEncoder(w).Encode(map[string]any{"openapi": "3.0.0", "info": map[string]any{"title": "ARGUS Gateway"}})
			return
		}
		_, _ = w.Write(a.OpenAPI)
	})
	root.HandleFunc("/v1/ping", func(w http.ResponseWriter, r *http.Request) {
		_, span := otel.Tracer("api-gateway").Start(r.Context(), "ping")
		defer span.End()
		writeJSON(w, http.StatusOK, map[string]any{"pong": true, "ts": time.Now().UTC().Format(time.RFC3339Nano)})
	})
	root.HandleFunc("POST /v1/incidents/{id}/resolve", a.handleResolveIncident)
	root.HandleFunc("POST /v1/copilot/ask", a.handleCopilotAsk)
	root.Handle("/", gwmux)

	handler := middleware.Chain(root, middleware.Deps{
		AuthDisabled: a.CFG.AuthDisabled,
		Validator:    a.Validator,
		OPA:          a.OPA,
		Limiter:      ratelimit.New(a.CFG.RateLimitRPS, a.CFG.RateLimitBurst),
		APIKeys:      a.CFG.APIKeys,
	})
	handler = otelhttp.NewHandler(handler, "api-gateway")

	httpServer := &http.Server{
		Addr:              a.CFG.HTTPAddr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	errCh := make(chan error, 1)
	go func() {
		errCh <- httpServer.ListenAndServe()
	}()
	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
		return nil
	case err := <-errCh:
		if err == http.ErrServerClosed {
			return nil
		}
		return err
	}
}

// NewGatewayFromConfig builds upstream clients + service.
func NewGatewayFromConfig(cfg config.Config) *service.Gateway {
	return &service.Gateway{
		Trino: &upstream.TrinoClient{
			BaseURL: cfg.TrinoURL,
			User:    cfg.TrinoUser,
			Catalog: cfg.TrinoCatalog,
			Schema:  cfg.TrinoSchema,
		},
		Incidents: &upstream.IncidentsClient{BaseURL: cfg.IncidentEngineURL},
		Dagster: &upstream.DagsterClient{
			GraphQLURL:     upstream.NormalizeGraphQLURL(cfg.DagsterGraphQLURL),
			LocationName:   cfg.DagsterLocation,
			RepositoryName: cfg.DagsterRepository,
			JobName:        cfg.DagsterJobName,
		},
		Stream: &upstream.TelemetryStreamer{
			Brokers:           cfg.KafkaBrokers,
			Topic:             cfg.KafkaTelemetryTopic,
			GroupID:           cfg.KafkaGroupID,
			SchemaRegistryURL: cfg.SchemaRegistryURL,
		},
	}
}

// LoadOpenAPI reads the swagger file from disk (or empty).
func LoadOpenAPI(path string) []byte {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	return b
}

func handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "api-gateway", "ready": true})
}

func (a *App) handleResolveIncident(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "incident id required"})
		return
	}
	inc, err := a.Gateway.Incidents.Resolve(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"incident": inc})
}

func (a *App) handleCopilotAsk(w http.ResponseWriter, r *http.Request) {
	base := strings.TrimRight(a.CFG.CopilotURL, "/")
	if base == "" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "AI_COPILOT_URL not configured"})
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "read body"})
		return
	}
	req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, base+"/copilot/ask", bytes.NewReader(body))
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]any{"error": err.Error()})
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	defer res.Body.Close()
	out, _ := io.ReadAll(io.LimitReader(res.Body, 4<<20))
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(res.StatusCode)
	_, _ = w.Write(out)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}
