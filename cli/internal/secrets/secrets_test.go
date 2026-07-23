package secrets_test

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/argus-platform/argus/cli/internal/secrets"
)

func TestParseKV(t *testing.T) {
	k, v, err := secrets.ParseKV(`XAI_API_KEY="sk-abc123"`)
	if err != nil || k != "XAI_API_KEY" || v != "sk-abc123" {
		t.Fatalf("got %s=%s err=%v", k, v, err)
	}
}

func TestSetReconcilesConflictingEnvFile(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "docker-compose.yml"), "services:\n  demo:\n    environment:\n      XAI_API_KEY: ${XAI_API_KEY}\n")
	writeFile(t, filepath.Join(root, "go.work"), "go 1.22\n")
	writeFile(t, filepath.Join(root, ".env.example"), "XAI_API_KEY=\n")
	writeFile(t, filepath.Join(root, ".env"), "XAI_API_KEY=old-primary\n")
	writeFile(t, filepath.Join(root, ".env.local"), "XAI_API_KEY=stale-other\nOTHER=1\n")

	res, err := secrets.Set(context.Background(), "XAI_API_KEY", "sk-new-value", secrets.SetOptions{
		RepoRoot:     root,
		SkipValidate: true,
		SkipRestart:  true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Reconciled) == 0 {
		t.Fatal("expected reconciliation of .env.local")
	}
	m, err := secrets.ReadEnvFile(filepath.Join(root, ".env.local"))
	if err != nil {
		t.Fatal(err)
	}
	if m["XAI_API_KEY"] != "sk-new-value" {
		t.Fatalf("env.local not reconciled: %q", m["XAI_API_KEY"])
	}
	if m["OTHER"] != "1" {
		t.Fatal("unrelated key clobbered")
	}
	primary, _ := secrets.ReadEnvFile(filepath.Join(root, ".env"))
	if primary["XAI_API_KEY"] != "sk-new-value" {
		t.Fatalf(".env=%q", primary["XAI_API_KEY"])
	}
}

func TestSetInvalidProviderKeyReportsRejection(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "docker-compose.yml"), "services: {}\n")
	writeFile(t, filepath.Join(root, "go.work"), "go 1.22\n")
	writeFile(t, filepath.Join(root, ".env.example"), "")

	_, err := secrets.Set(context.Background(), "XAI_API_KEY", "sk-fake-bad-key", secrets.SetOptions{
		RepoRoot:    root,
		SkipRestart: true,
		Validator: func(ctx context.Context, key, value string, env map[string]string) secrets.ValidationResult {
			return secrets.ValidationResult{
				Key:      key,
				Provider: "xAI",
				OK:       false,
				Status:   401,
				Message:  "XAI_API_KEY rejected by provider (401)",
			}
		},
	})
	if err == nil {
		t.Fatal("expected validation error")
	}
	if !strings.Contains(err.Error(), "rejected by provider (401)") {
		t.Fatalf("unclear error: %v", err)
	}
	// Key should still be written (user is told explicitly).
	m, _ := secrets.ReadEnvFile(filepath.Join(root, ".env"))
	if m["XAI_API_KEY"] != "sk-fake-bad-key" {
		t.Fatalf("expected key written despite rejection, got %q", m["XAI_API_KEY"])
	}
}

func TestDoctorMissingAndDuplicate(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "docker-compose.yml"), "services: {}\n")
	writeFile(t, filepath.Join(root, "go.work"), "go 1.22\n")
	writeFile(t, filepath.Join(root, ".env.example"), "XAI_API_KEY=\n")
	writeFile(t, filepath.Join(root, ".env"), "OPENAI_API_KEY=from-env\n")
	writeFile(t, filepath.Join(root, ".env.staging"), "OPENAI_API_KEY=from-staging\n")
	// Code references a missing key.
	_ = os.MkdirAll(filepath.Join(root, "svc"), 0o755)
	writeFile(t, filepath.Join(root, "svc", "main.go"), "package main\nimport \"os\"\nfunc main() { _ = os.Getenv(\"ANTHROPIC_API_KEY\") }\n")

	rep, err := secrets.Doctor(context.Background(), secrets.DoctorOptions{
		RepoRoot:     root,
		SkipValidate: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	var missing, dup bool
	for _, k := range rep.Keys {
		if k.Key == "ANTHROPIC_API_KEY" && k.Missing && k.Status == "fail" {
			missing = true
		}
		if k.Key == "OPENAI_API_KEY" && len(k.Conflicts) > 0 && k.Status == "fail" {
			dup = true
		}
	}
	if !missing {
		t.Fatalf("expected missing ANTHROPIC_API_KEY flag, report=%+v", rep.Keys)
	}
	if !dup {
		t.Fatalf("expected duplicate OPENAI_API_KEY conflict, report=%+v", rep.Keys)
	}
	if rep.OK() {
		t.Fatal("doctor should not be OK")
	}
}

func writeFile(t *testing.T, path, body string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}
