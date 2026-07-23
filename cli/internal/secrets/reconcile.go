package secrets

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
)

// Change records a reconciliation edit.
type Change struct {
	Path    string
	Kind    string
	Before  string
	After   string
	Message string
}

// Reconcile updates every conflicting definition of key to match value
// (or strips hardcoded fallbacks so env is the sole source).
func Reconcile(root, key, value string, locs []Location) ([]Change, error) {
	var changes []Change
	for _, loc := range locs {
		if loc.Path == ".env" {
			continue // primary store handled by UpsertEnvFile
		}
		if loc.Value == value {
			continue // already consistent
		}
		abs := filepath.Join(root, loc.Path)
		switch loc.Kind {
		case "env_file":
			_, err := UpsertEnvFile(abs, key, value)
			if err != nil {
				return changes, err
			}
			changes = append(changes, Change{
				Path:    loc.Path,
				Kind:    loc.Kind,
				Before:  loc.Value,
				After:   value,
				Message: fmt.Sprintf("updated %s to match .env", loc.Path),
			})
		case "compose_default":
			ch, err := reconcileComposeDefault(abs, key, value, loc)
			if err != nil {
				return changes, err
			}
			if ch != nil {
				changes = append(changes, *ch)
			}
		case "go_fallback":
			ch, err := reconcileGoFallback(abs, key, loc)
			if err != nil {
				return changes, err
			}
			if ch != nil {
				changes = append(changes, *ch)
			}
		case "python_fallback":
			ch, err := reconcilePyFallback(abs, key, loc)
			if err != nil {
				return changes, err
			}
			if ch != nil {
				changes = append(changes, *ch)
			}
		}
	}
	return changes, nil
}

func reconcileComposeDefault(path, key, value string, loc Location) (*Change, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	old := string(b)
	// Prefer forcing env (no embedded secret default): ${KEY} instead of ${KEY:-old}
	pat := regexp.MustCompile(`\$\{` + regexp.QuoteMeta(key) + `:-([^}]*)\}`)
	newBody := pat.ReplaceAllString(old, `${`+key+`}`)
	if newBody == old {
		// Fallback: update the default literal to the new value.
		pat2 := regexp.MustCompile(`\$\{` + regexp.QuoteMeta(key) + `:-` + regexp.QuoteMeta(loc.Value) + `\}`)
		newBody = pat2.ReplaceAllString(old, `${`+key+`:-`+value+`}`)
	}
	if newBody == old {
		return nil, nil
	}
	if err := os.WriteFile(path, []byte(newBody), 0o644); err != nil {
		return nil, err
	}
	return &Change{
		Path:    "docker-compose.yml",
		Kind:    "compose_default",
		Before:  loc.Snippet,
		After:   "${" + key + "}",
		Message: fmt.Sprintf("removed compose default for %s (now reads from env only)", key),
	}, nil
}

func reconcileGoFallback(path, key string, loc Location) (*Change, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	old := string(b)
	// getenv("KEY", "fallback") → getenv("KEY", "")
	// os.Getenv doesn't take fallback in stdlib — only our getenv helper.
	re := regexp.MustCompile(`(getenv\(\s*"` + regexp.QuoteMeta(key) + `"\s*,\s*)"[^"]*"`)
	newBody := re.ReplaceAllString(old, `${1}""`)
	if newBody == old {
		re2 := regexp.MustCompile(`(os\.Getenv\(\s*"` + regexp.QuoteMeta(key) + `"\s*\))`)
		// os.Getenv has no fallback — nothing to strip; leave as-is.
		_ = re2
		return nil, nil
	}
	if err := os.WriteFile(path, []byte(newBody), 0o644); err != nil {
		return nil, err
	}
	return &Change{
		Path:    loc.Path,
		Kind:    "go_fallback",
		Before:  loc.Snippet,
		After:   `getenv("` + key + `", "")`,
		Message: fmt.Sprintf("%s:%d removed hardcoded fallback for %s", loc.Path, loc.Line, key),
	}, nil
}

func reconcilePyFallback(path, key string, loc Location) (*Change, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	old := string(b)
	re := regexp.MustCompile(`(os\.(?:environ\.get|getenv)\(\s*["']` + regexp.QuoteMeta(key) + `["']\s*,\s*)["'][^"']*["']`)
	newBody := re.ReplaceAllString(old, `${1}""`)
	if newBody == old {
		return nil, nil
	}
	if err := os.WriteFile(path, []byte(newBody), 0o644); err != nil {
		return nil, err
	}
	return &Change{
		Path:    loc.Path,
		Kind:    "python_fallback",
		Before:  loc.Snippet,
		After:   `os.environ.get("` + key + `", "")`,
		Message: fmt.Sprintf("%s:%d removed hardcoded fallback for %s", loc.Path, loc.Line, key),
	}, nil
}

func conflicting(locs []Location, primary string, value string) []Location {
	var out []Location
	for _, l := range locs {
		if l.Path == primary {
			continue
		}
		if l.Value != "" && l.Value != value {
			out = append(out, l)
		}
	}
	return out
}
