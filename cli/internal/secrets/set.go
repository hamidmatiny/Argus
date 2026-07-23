package secrets

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// SetOptions controls secrets set behavior.
type SetOptions struct {
	RepoRoot     string
	SkipValidate bool
	SkipRestart  bool
	Stdout       io.Writer
	Stderr       io.Writer
	// ComposeRunner overrides docker compose for tests.
	ComposeRunner func(ctx context.Context, root string, services []string) error
	// Validator overrides live validation for tests.
	Validator func(ctx context.Context, key, value string, env map[string]string) ValidationResult
}

// SetResult is the full outcome of a set operation.
type SetResult struct {
	Key            string
	ValueRedacted  string
	EnvPath        string
	EnvWritten     bool
	Reconciled     []Change
	Validation     *ValidationResult
	Restarted      []string
	RestartSkipped bool
}

// Set writes the secret, reconciles conflicts, validates, and restarts consumers.
func Set(ctx context.Context, key, value string, opts SetOptions) (*SetResult, error) {
	root, err := FindRepoRoot(opts.RepoRoot)
	if err != nil {
		return nil, err
	}
	envPath := filepath.Join(root, ".env")
	res := &SetResult{
		Key:           key,
		ValueRedacted: redact(value),
		EnvPath:       envPath,
	}

	written, err := UpsertEnvFile(envPath, key, value)
	if err != nil {
		return res, fmt.Errorf("write .env: %w", err)
	}
	res.EnvWritten = written

	// Scan before/after style: scan all defs and reconcile conflicts.
	locs, err := ScanDefinitions(root, key)
	if err != nil {
		return res, err
	}
	conflicts := conflicting(locs, ".env", value)
	changes, err := Reconcile(root, key, value, conflicts)
	if err != nil {
		return res, fmt.Errorf("reconcile: %w", err)
	}
	res.Reconciled = changes

	// Re-scan to ensure single value.
	after, err := ScanDefinitions(root, key)
	if err != nil {
		return res, err
	}
	still := conflicting(after, ".env", value)
	if len(still) > 0 {
		var b strings.Builder
		fmt.Fprintf(&b, "still have conflicting definitions for %s after reconcile:\n", key)
		for _, l := range still {
			fmt.Fprintf(&b, "  - %s value=%q\n", fmtLoc(l), redact(l.Value))
		}
		return res, fmt.Errorf("%s", b.String())
	}

	envMap, _ := ReadEnvFile(envPath)
	if IsProviderKey(key) && !opts.SkipValidate {
		validator := opts.Validator
		if validator == nil {
			validator = ValidateProviderKey
		}
		v := validator(ctx, key, value, envMap)
		res.Validation = &v
		if !v.OK {
			return res, fmt.Errorf("%s", v.Message)
		}
	}

	if !opts.SkipRestart {
		services, err := ComposeServicesForKey(root, key)
		if err != nil {
			return res, err
		}
		if len(services) == 0 {
			res.RestartSkipped = true
		} else {
			runner := opts.ComposeRunner
			if runner == nil {
				runner = defaultComposeRestart
			}
			if err := runner(ctx, root, services); err != nil {
				return res, fmt.Errorf("restart services %v: %w", services, err)
			}
			res.Restarted = services
		}
	}
	return res, nil
}

func defaultComposeRestart(ctx context.Context, root string, services []string) error {
	args := append([]string{"compose", "up", "-d", "--build"}, services...)
	cmd := exec.CommandContext(ctx, "docker", args...)
	cmd.Dir = root
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func redact(v string) string {
	if v == "" {
		return ""
	}
	if len(v) <= 8 {
		return "****"
	}
	return v[:4] + "…" + v[len(v)-4:]
}

// PrintSetReport writes a human-readable summary.
func PrintSetReport(w io.Writer, res *SetResult) {
	if w == nil || res == nil {
		return
	}
	fmt.Fprintf(w, "secrets set %s=%s\n", res.Key, res.ValueRedacted)
	if res.EnvWritten {
		fmt.Fprintf(w, "  wrote %s\n", res.EnvPath)
	} else {
		fmt.Fprintf(w, "  .env already had matching value\n")
	}
	if len(res.Reconciled) == 0 {
		fmt.Fprintf(w, "  reconcile: no conflicting copies\n")
	} else {
		fmt.Fprintf(w, "  reconcile: %d change(s)\n", len(res.Reconciled))
		for _, c := range res.Reconciled {
			fmt.Fprintf(w, "    • %s\n", c.Message)
			if c.Before != "" {
				fmt.Fprintf(w, "      before: %s\n", truncate(c.Before, 100))
			}
			if c.After != "" {
				fmt.Fprintf(w, "      after:  %s\n", truncate(c.After, 100))
			}
		}
	}
	if res.Validation != nil {
		if res.Validation.OK {
			fmt.Fprintf(w, "  validate: PASS — %s\n", res.Validation.Message)
		} else {
			fmt.Fprintf(w, "  validate: FAIL — %s\n", res.Validation.Message)
		}
	}
	if res.RestartSkipped {
		fmt.Fprintf(w, "  restart: no compose services reference %s\n", res.Key)
	} else if len(res.Restarted) > 0 {
		fmt.Fprintf(w, "  restart: %s\n", strings.Join(res.Restarted, ", "))
	}
}

func truncate(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
