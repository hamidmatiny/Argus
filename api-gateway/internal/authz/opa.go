package authz

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/open-policy-agent/opa/rego"
)

// Engine evaluates gateway Rego allow decisions.
type Engine struct {
	query rego.PreparedEvalQuery
}

// Input is the OPA evaluation document.
type Input struct {
	Role   string `json:"role"`
	Method string `json:"method"`
	Path   string `json:"path"`
}

// Load reads *.rego from dir and prepares data.argus.gateway.allow.
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
		body, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		modules[e.Name()] = string(body)
	}
	if len(modules) == 0 {
		return nil, fmt.Errorf("no .rego files in %s", dir)
	}
	opts := []func(*rego.Rego){rego.Query("data.argus.gateway.allow")}
	for name, body := range modules {
		opts = append(opts, rego.Module(name, body))
	}
	prepared, err := rego.New(opts...).PrepareForEval(ctx)
	if err != nil {
		return nil, fmt.Errorf("prepare rego: %w", err)
	}
	return &Engine{query: prepared}, nil
}

// Allow returns whether the request is authorized.
func (e *Engine) Allow(ctx context.Context, in Input) (bool, error) {
	rs, err := e.query.Eval(ctx, rego.EvalInput(in))
	if err != nil {
		return false, err
	}
	if len(rs) == 0 || len(rs[0].Expressions) == 0 {
		return false, nil
	}
	allowed, _ := rs[0].Expressions[0].Value.(bool)
	return allowed, nil
}
