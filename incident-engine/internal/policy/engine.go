// Package policy evaluates incident trip/routing decisions with OPA + Rego.
package policy

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/open-policy-agent/opa/rego"

	"github.com/argus-platform/argus/incident-engine/internal/models"
)

// Engine compiles and evaluates the shipped Rego policies.
type Engine struct {
	query rego.PreparedEvalQuery
}

// Load reads all *.rego files from dir and prepares a query for the decision.
func Load(ctx context.Context, dir string) (*Engine, error) {
	modules := map[string]string{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read policy dir: %w", err)
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".rego") {
			continue
		}
		path := filepath.Join(dir, e.Name())
		body, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		modules[e.Name()] = string(body)
	}
	if len(modules) == 0 {
		return nil, fmt.Errorf("no .rego files in %s", dir)
	}

	opts := []func(*rego.Rego){
		rego.Query(`{
			"trip": data.argus.incident.trip,
			"route": data.argus.incident.route,
			"severity": data.argus.incident.severity,
			"reasons": data.argus.incident.reasons
		}`),
	}
	for name, body := range modules {
		opts = append(opts, rego.Module(name, body))
	}
	prepared, err := rego.New(opts...).PrepareForEval(ctx)
	if err != nil {
		return nil, fmt.Errorf("prepare rego: %w", err)
	}
	return &Engine{query: prepared}, nil
}

// Evaluate runs policies against input and returns a structured decision.
func (e *Engine) Evaluate(ctx context.Context, in models.PolicyInput) (models.PolicyDecision, time.Duration, error) {
	start := time.Now()
	rs, err := e.query.Eval(ctx, rego.EvalInput(in))
	elapsed := time.Since(start)
	if err != nil {
		return models.PolicyDecision{}, elapsed, fmt.Errorf("eval: %w", err)
	}
	if len(rs) == 0 || len(rs[0].Expressions) == 0 {
		return models.PolicyDecision{}, elapsed, fmt.Errorf("empty policy result")
	}
	raw, ok := rs[0].Expressions[0].Value.(map[string]any)
	if !ok {
		return models.PolicyDecision{}, elapsed, fmt.Errorf("unexpected result type %T", rs[0].Expressions[0].Value)
	}
	dec := models.PolicyDecision{
		Trip:     asBool(raw["trip"]),
		Route:    asString(raw["route"], "slack"),
		Severity: asString(raw["severity"], "warning"),
		Reasons:  asStringSet(raw["reasons"]),
	}
	return dec, elapsed, nil
}

func asBool(v any) bool {
	b, _ := v.(bool)
	return b
}

func asString(v any, fallback string) string {
	s, ok := v.(string)
	if !ok || s == "" {
		return fallback
	}
	return s
}

func asStringSet(v any) []string {
	switch t := v.(type) {
	case []any:
		out := make([]string, 0, len(t))
		for _, item := range t {
			if s, ok := item.(string); ok && s != "" {
				out = append(out, s)
			}
		}
		return out
	case map[string]any:
		out := make([]string, 0, len(t))
		for k := range t {
			out = append(out, k)
		}
		return out
	default:
		return nil
	}
}
