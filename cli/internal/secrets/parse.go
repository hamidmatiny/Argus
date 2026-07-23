package secrets

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ParseKV splits KEY=VALUE (VALUE may be quoted).
func ParseKV(raw string) (key, value string, err error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", "", fmt.Errorf("empty KEY=VALUE")
	}
	key, value, ok := strings.Cut(raw, "=")
	if !ok {
		return "", "", fmt.Errorf("expected KEY=VALUE, got %q", raw)
	}
	key = strings.TrimSpace(key)
	value = strings.TrimSpace(value)
	if key == "" {
		return "", "", fmt.Errorf("empty key name")
	}
	if !validKeyName(key) {
		return "", "", fmt.Errorf("invalid key name %q (use A-Z, 0-9, _)", key)
	}
	value = unquote(value)
	return key, value, nil
}

func validKeyName(k string) bool {
	if k == "" {
		return false
	}
	for i, r := range k {
		switch {
		case r >= 'A' && r <= 'Z':
		case r >= 'a' && r <= 'z':
		case r >= '0' && r <= '9' && i > 0:
		case r == '_':
		default:
			return false
		}
	}
	return true
}

func unquote(v string) string {
	if len(v) >= 2 {
		if (v[0] == '"' && v[len(v)-1] == '"') || (v[0] == '\'' && v[len(v)-1] == '\'') {
			return v[1 : len(v)-1]
		}
	}
	return v
}

// FindRepoRoot walks upward from start (or cwd) looking for docker-compose.yml + go.work.
func FindRepoRoot(explicit string) (string, error) {
	if explicit != "" {
		abs, err := filepath.Abs(explicit)
		if err != nil {
			return "", err
		}
		return abs, nil
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := wd
	for {
		compose := filepath.Join(dir, "docker-compose.yml")
		work := filepath.Join(dir, "go.work")
		if fileExists(compose) && fileExists(work) {
			return dir, nil
		}
		// Prefer docker-compose alone if at an Argus-like root.
		if fileExists(compose) && fileExists(filepath.Join(dir, ".env.example")) {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return "", fmt.Errorf("could not find ARGUS repo root from %s (looked for docker-compose.yml)", wd)
}

func fileExists(p string) bool {
	st, err := os.Stat(p)
	return err == nil && !st.IsDir()
}

// ProviderPrefixes are live-validated when set.
var ProviderPrefixes = []string{
	"XAI_",
	"ANTHROPIC_",
	"OPENAI_",
	"LLM_API_KEY",
	"GROQ_",
	"COHERE_",
	"MISTRAL_",
	"GOOGLE_API_KEY",
	"GEMINI_",
}

// IsProviderKey reports whether key should be live-validated.
func IsProviderKey(key string) bool {
	if key == "LLM_API_KEY" || key == "GOOGLE_API_KEY" {
		return true
	}
	for _, p := range ProviderPrefixes {
		if strings.HasSuffix(p, "_") && strings.HasPrefix(key, p) {
			return true
		}
	}
	return false
}
