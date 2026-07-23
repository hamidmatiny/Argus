package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds api-gateway runtime settings.
type Config struct {
	HTTPAddr string
	GRPCAddr string

	AuthDisabled bool
	OIDCIssuer   string
	OIDCAudience string
	JWKSURL      string

	PolicyDir string

	IncidentEngineURL string
	TrinoURL          string
	TrinoUser         string
	TrinoCatalog      string
	TrinoSchema       string
	DagsterGraphQLURL string
	DagsterLocation   string
	DagsterRepository string
	DagsterJobName    string

	KafkaBrokers          []string
	KafkaTelemetryTopic   string
	KafkaGroupID          string
	SchemaRegistryURL     string

	RateLimitRPS   float64
	RateLimitBurst int
	APIKeys        map[string]string // key -> role override (optional)

	OTELEndpoint string
}

// Load reads configuration from the environment.
func Load() Config {
	return Config{
		HTTPAddr:              getenv("API_GATEWAY_ADDR", ":8099"),
		GRPCAddr:              getenv("API_GATEWAY_GRPC_ADDR", ":9099"),
		AuthDisabled:          getenvBool("API_GATEWAY_AUTH_DISABLED", false),
		OIDCIssuer:            getenv("OIDC_ISSUER_URL", "http://localhost:8085/realms/argus"),
		OIDCAudience:          getenv("OIDC_AUDIENCE", "argus-gateway"),
		JWKSURL:               getenv("OIDC_JWKS_URL", ""),
		PolicyDir:             getenv("API_GATEWAY_POLICY_DIR", "policies"),
		IncidentEngineURL:     getenv("INCIDENT_ENGINE_URL", "http://incident-engine:8098"),
		TrinoURL:              getenv("TRINO_URL", "http://trino:8080"),
		TrinoUser:             getenv("TRINO_USER", "argus"),
		TrinoCatalog:          getenv("TRINO_CATALOG", "iceberg"),
		TrinoSchema:           getenv("TRINO_SCHEMA", "fleet"),
		DagsterGraphQLURL:     getenv("DAGSTER_GRAPHQL_URL", "http://dagster-webserver:3000/graphql"),
		DagsterLocation:       getenv("DAGSTER_LOCATION_NAME", "argus_orchestration.definitions"),
		DagsterRepository:     getenv("DAGSTER_REPOSITORY_NAME", "__repository__"),
		DagsterJobName:        getenv("DAGSTER_JOB_NAME", "drift_retrain_job"),
		KafkaBrokers:          splitCSV(getenv("KAFKA_BROKERS", "redpanda:9092")),
		KafkaTelemetryTopic:   getenv("QA_VALIDATED_TOPIC", "telemetry.validated"),
		KafkaGroupID:          getenv("API_GATEWAY_KAFKA_GROUP_ID", "argus-api-gateway"),
		SchemaRegistryURL:     getenv("SCHEMA_REGISTRY_URL", "http://redpanda:8081"),
		RateLimitRPS:          getenvFloat("API_GATEWAY_RATE_LIMIT_RPS", 20),
		RateLimitBurst:        getenvInt("API_GATEWAY_RATE_LIMIT_BURST", 40),
		APIKeys:               parseAPIKeys(getenv("API_GATEWAY_API_KEYS", "demo-viewer:viewer,demo-operator:operator,demo-admin:admin")),
		OTELEndpoint:          os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
	}
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getenvBool(k string, def bool) bool {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}

func getenvInt(k string, def int) int {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func getenvFloat(k string, def float64) float64 {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return def
	}
	return f
}

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func parseAPIKeys(s string) map[string]string {
	out := map[string]string{}
	for _, part := range splitCSV(s) {
		k, v, ok := strings.Cut(part, ":")
		if !ok {
			continue
		}
		out[strings.TrimSpace(k)] = strings.TrimSpace(v)
	}
	return out
}

// JWKSRefresh is the default JWKS cache TTL.
const JWKSRefresh = 5 * time.Minute
