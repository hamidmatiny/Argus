package secrets

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// UpsertEnvFile sets KEY=VALUE in path, replacing an existing assignment.
func UpsertEnvFile(path, key, value string) (changed bool, err error) {
	var lines []string
	existing := false
	if b, err := os.ReadFile(path); err == nil {
		sc := bufio.NewScanner(strings.NewReader(string(b)))
		// Allow long lines.
		buf := make([]byte, 0, 64*1024)
		sc.Buffer(buf, 1024*1024)
		for sc.Scan() {
			line := sc.Text()
			k, _, ok := parseEnvLine(line)
			if ok && k == key {
				lines = append(lines, formatEnvLine(key, value))
				existing = true
				changed = true
				continue
			}
			lines = append(lines, line)
		}
		if err := sc.Err(); err != nil {
			return false, err
		}
	} else if !os.IsNotExist(err) {
		return false, err
	}
	if !existing {
		if len(lines) > 0 && lines[len(lines)-1] != "" {
			lines = append(lines, "")
		}
		lines = append(lines, formatEnvLine(key, value))
		changed = true
	}
	body := strings.Join(lines, "\n")
	if !strings.HasSuffix(body, "\n") {
		body += "\n"
	}
	return changed, os.WriteFile(path, []byte(body), 0o600)
}

// ReadEnvFile returns KEY→value for assignments (comments/blank skipped).
func ReadEnvFile(path string) (map[string]string, error) {
	out := map[string]string{}
	b, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return out, nil
		}
		return nil, err
	}
	sc := bufio.NewScanner(strings.NewReader(string(b)))
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 1024*1024)
	for sc.Scan() {
		k, v, ok := parseEnvLine(sc.Text())
		if ok {
			out[k] = v
		}
	}
	return out, sc.Err()
}

func parseEnvLine(line string) (key, value string, ok bool) {
	trim := strings.TrimSpace(line)
	if trim == "" || strings.HasPrefix(trim, "#") {
		return "", "", false
	}
	// Optional "export KEY=..."
	trim = strings.TrimPrefix(trim, "export ")
	trim = strings.TrimSpace(trim)
	k, v, cut := strings.Cut(trim, "=")
	if !cut {
		return "", "", false
	}
	k = strings.TrimSpace(k)
	if !validKeyName(k) {
		return "", "", false
	}
	return k, unquote(strings.TrimSpace(v)), true
}

func formatEnvLine(key, value string) string {
	if needsQuotes(value) {
		escaped := strings.ReplaceAll(value, `\`, `\\`)
		escaped = strings.ReplaceAll(escaped, `"`, `\"`)
		return fmt.Sprintf(`%s="%s"`, key, escaped)
	}
	return key + "=" + value
}

func needsQuotes(v string) bool {
	if v == "" {
		return true
	}
	return strings.ContainsAny(v, " \t#\"'\\$")
}
