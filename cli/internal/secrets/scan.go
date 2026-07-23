package secrets

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Location is a place a key is defined or defaulted.
type Location struct {
	Path    string // relative to repo root
	Kind    string // env_file | compose_default | go_fallback | python_fallback
	Value   string // literal value if known; empty if reference-only
	Line    int
	Snippet string
}

var (
	reComposeDefault = regexp.MustCompile(`\$\{([A-Z][A-Z0-9_]*)(:-([^}]*))?\}`)
	reGoGetenv       = regexp.MustCompile(`(?:os\.Getenv|getenv)\(\s*"([A-Z][A-Z0-9_]*)"\s*(?:,\s*"([^"]*)")?\s*\)`)
	rePyGetenv       = regexp.MustCompile(`os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]*)["']\s*(?:,\s*["']([^"']*)["'])?\s*\)`)
)

// ScanDefinitions finds every literal or defaulted definition of key under root.
func ScanDefinitions(root, key string) ([]Location, error) {
	var out []Location
	envFiles, err := filepath.Glob(filepath.Join(root, ".env*"))
	if err != nil {
		return nil, err
	}
	for _, p := range envFiles {
		base := filepath.Base(p)
		if base == ".env" {
			// Primary store — still reported for doctor, but set reconciles others.
		}
		m, err := ReadEnvFile(p)
		if err != nil {
			continue
		}
		if v, ok := m[key]; ok {
			rel, _ := filepath.Rel(root, p)
			out = append(out, Location{
				Path:    rel,
				Kind:    "env_file",
				Value:   v,
				Snippet: formatEnvLine(key, v),
			})
		}
	}

	composePath := filepath.Join(root, "docker-compose.yml")
	if b, err := os.ReadFile(composePath); err == nil {
		lines := strings.Split(string(b), "\n")
		for i, line := range lines {
			for _, m := range reComposeDefault.FindAllStringSubmatch(line, -1) {
				if m[1] != key {
					continue
				}
				def := ""
				if len(m) > 3 {
					def = m[3]
				}
				if def == "" && !strings.Contains(line, key) {
					continue
				}
				// Reference without default is not a conflicting definition.
				if m[2] == "" {
					continue
				}
				out = append(out, Location{
					Path:    "docker-compose.yml",
					Kind:    "compose_default",
					Value:   def,
					Line:    i + 1,
					Snippet: strings.TrimSpace(line),
				})
			}
		}
	}

	err = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			name := d.Name()
			switch name {
			case ".git", "node_modules", ".venv", "vendor", "dist", "build",
				"shared/gen", ".cursor", "bin":
				return filepath.SkipDir
			}
			if strings.HasPrefix(name, ".") && path != root {
				// Skip hidden dirs except we already handle .env at root.
				if name != "." {
					return filepath.SkipDir
				}
			}
			return nil
		}
		ext := filepath.Ext(path)
		switch ext {
		case ".go":
			locs, _ := scanGoFile(root, path, key)
			out = append(out, locs...)
		case ".py":
			locs, _ := scanPyFile(root, path, key)
			out = append(out, locs...)
		}
		return nil
	})
	return out, err
}

func scanGoFile(root, path, key string) ([]Location, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	rel, _ := filepath.Rel(root, path)
	var out []Location
	lines := strings.Split(string(b), "\n")
	for i, line := range lines {
		for _, m := range reGoGetenv.FindAllStringSubmatch(line, -1) {
			if m[1] != key {
				continue
			}
			if len(m) < 3 || m[2] == "" {
				continue // getenv without fallback — not a conflicting definition
			}
			out = append(out, Location{
				Path:    rel,
				Kind:    "go_fallback",
				Value:   m[2],
				Line:    i + 1,
				Snippet: strings.TrimSpace(line),
			})
		}
	}
	return out, nil
}

func scanPyFile(root, path, key string) ([]Location, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	rel, _ := filepath.Rel(root, path)
	var out []Location
	lines := strings.Split(string(b), "\n")
	for i, line := range lines {
		for _, m := range rePyGetenv.FindAllStringSubmatch(line, -1) {
			if m[1] != key {
				continue
			}
			if len(m) < 3 || m[2] == "" {
				continue
			}
			out = append(out, Location{
				Path:    rel,
				Kind:    "python_fallback",
				Value:   m[2],
				Line:    i + 1,
				Snippet: strings.TrimSpace(line),
			})
		}
	}
	return out, nil
}

// ScanReferences finds code that reads key (with or without default).
func ScanReferences(root string) (map[string][]Location, error) {
	refs := map[string][]Location{}
	err := filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			if d != nil && d.IsDir() {
				switch d.Name() {
				case ".git", "node_modules", ".venv", "vendor", "shared/gen", ".cursor":
					return filepath.SkipDir
				}
			}
			return nil
		}
		ext := filepath.Ext(path)
		var re *regexp.Regexp
		kind := ""
		switch ext {
		case ".go":
			re = reGoGetenv
			kind = "go_ref"
		case ".py":
			re = rePyGetenv
			kind = "python_ref"
		default:
			return nil
		}
		b, err := os.ReadFile(path)
		if err != nil {
			return nil
		}
		rel, _ := filepath.Rel(root, path)
		lines := strings.Split(string(b), "\n")
		for i, line := range lines {
			for _, m := range re.FindAllStringSubmatch(line, -1) {
				key := m[1]
				val := ""
				if len(m) > 2 {
					val = m[2]
				}
				refs[key] = append(refs[key], Location{
					Path:    rel,
					Kind:    kind,
					Value:   val,
					Line:    i + 1,
					Snippet: strings.TrimSpace(line),
				})
			}
		}
		return nil
	})
	return refs, err
}

// ComposeServicesForKey returns service names whose environment references key.
func ComposeServicesForKey(root, key string) ([]string, error) {
	b, err := os.ReadFile(filepath.Join(root, "docker-compose.yml"))
	if err != nil {
		return nil, err
	}
	lines := strings.Split(string(b), "\n")
	var services []string
	var current string
	inServices := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "services:" {
			inServices = true
			continue
		}
		if !inServices {
			continue
		}
		// Top-level key under services (two-space indent, name:)
		if strings.HasPrefix(line, "  ") && !strings.HasPrefix(line, "   ") && strings.HasSuffix(trimmed, ":") && !strings.Contains(trimmed, " ") {
			name := strings.TrimSuffix(trimmed, ":")
			if name != "" && !strings.HasPrefix(name, "#") {
				current = name
			}
			continue
		}
		if current == "" {
			continue
		}
		if strings.Contains(line, key) {
			// Avoid matching substrings of longer keys.
			if strings.Contains(line, "${"+key) || strings.Contains(line, key+":") || strings.Contains(line, key+"=") {
				services = appendUnique(services, current)
			}
		}
	}
	return services, nil
}

func appendUnique(ss []string, s string) []string {
	for _, x := range ss {
		if x == s {
			return ss
		}
	}
	return append(ss, s)
}

func fmtLoc(l Location) string {
	if l.Line > 0 {
		return fmt.Sprintf("%s:%d (%s)", l.Path, l.Line, l.Kind)
	}
	return fmt.Sprintf("%s (%s)", l.Path, l.Kind)
}
