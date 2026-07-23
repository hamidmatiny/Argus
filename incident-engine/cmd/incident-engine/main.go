// Command incident-engine correlates QA metrics and drift incidents into
// per-vehicle circuit breakers with OPA/Rego policies and webhook escalation.
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

	"github.com/argus-platform/argus/incident-engine/internal/api"
	"github.com/argus-platform/argus/incident-engine/internal/circuitbreaker"
	"github.com/argus-platform/argus/incident-engine/internal/config"
	"github.com/argus-platform/argus/incident-engine/internal/engine"
	kafkabus "github.com/argus-platform/argus/incident-engine/internal/kafka"
	"github.com/argus-platform/argus/incident-engine/internal/metrics"
	"github.com/argus-platform/argus/incident-engine/internal/policy"
	"github.com/argus-platform/argus/incident-engine/internal/webhook"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	cfg := config.Load()
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck(cfg.HTTPAddr))
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	policyDir := cfg.PolicyDir
	if !filepath.IsAbs(policyDir) {
		if _, err := os.Stat(policyDir); err != nil {
			// Distroless image ships policies under /etc/argus/policies.
			if _, err2 := os.Stat("/etc/argus/policies"); err2 == nil {
				policyDir = "/etc/argus/policies"
			}
		}
	}

	policies, err := policy.Load(ctx, policyDir)
	if err != nil {
		slog.Error("policy_load_failed", "err", err, "dir", policyDir)
		os.Exit(1)
	}

	breakers := circuitbreaker.NewStore(circuitbreaker.Config{
		OpenCooldown:        cfg.OpenCooldown,
		HalfOpenSuccessNeed: cfg.HalfOpenSuccessNeed,
	})
	m := metrics.New()
	if err := kafkabus.EnsureTopic(cfg.KafkaBrokers, cfg.EscalatedTopic); err != nil {
		slog.Warn("ensure_topic_failed", "topic", cfg.EscalatedTopic, "err", err)
	}
	producer := kafkabus.NewProducer(cfg.KafkaBrokers, cfg.EscalatedTopic)

	mockURL := ""
	if cfg.EnableMockWebhook && cfg.SlackWebhookURL == "" && cfg.PagerDutyWebhookURL == "" {
		// Point dispatcher at this process's mock sink.
		host := "127.0.0.1" + cfg.HTTPAddr
		if cfg.HTTPAddr != "" && cfg.HTTPAddr[0] == ':' {
			host = "127.0.0.1" + cfg.HTTPAddr
		}
		mockURL = "http://" + host + "/webhooks/mock"
	}
	dispatcher := webhook.NewDispatcher(cfg.SlackWebhookURL, cfg.PagerDutyWebhookURL, mockURL)

	corr := engine.NewCorrelator(cfg, policies, breakers, producer, dispatcher, m)

	qaConsumer := kafkabus.NewConsumer(cfg.KafkaBrokers, cfg.QAMetricsTopic, cfg.KafkaGroupID+"-qa")
	incConsumer := kafkabus.NewConsumer(cfg.KafkaBrokers, cfg.IncidentsRawTopic, cfg.KafkaGroupID+"-incidents")

	go kafkabus.RunLoop(ctx, qaConsumer, "qa_metrics", corr.HandleQA)
	go kafkabus.RunLoop(ctx, incConsumer, "incidents_raw", corr.HandleIncident)

	srv := api.New(corr, dispatcher, func() bool { return true })
	httpServer := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		slog.Info("http_listen", "addr", cfg.HTTPAddr, "mock_webhook", mockURL)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("http_failed", "err", err)
			stop()
		}
	}()

	<-ctx.Done()
	slog.Info("shutting_down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(shutdownCtx)
	_ = qaConsumer.Close()
	_ = incConsumer.Close()
	_ = producer.Close()
}

func runHealthcheck(addr string) int {
	if addr == "" {
		addr = ":8098"
	}
	url := "http://127.0.0.1" + addr + "/health"
	if addr[0] != ':' {
		url = "http://" + addr + "/health"
	}
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return 1
	}
	return 0
}
