package secrets

import (
	"context"
	"fmt"
	"io"
	"path/filepath"
	"sort"
	"strings"
)

// DoctorOptions controls secrets doctor.
type DoctorOptions struct {
	RepoRoot     string
	SkipValidate bool
	Validator    func(ctx context.Context, key, value string, env map[string]string) ValidationResult
}

// KeyReport is the per-key doctor row.
type KeyReport struct {
	Key        string
	Status     string // pass | fail | warn | skip
	Missing    bool
	Conflicts  []string
	Validation *ValidationResult
	Detail     string
}

// DoctorReport is the consolidated audit.
type DoctorReport struct {
	Keys []KeyReport
}

// OK is true when every key passed.
func (r *DoctorReport) OK() bool {
	for _, k := range r.Keys {
		if k.Status == "fail" {
			return false
		}
	}
	return true
}

func isSecretish(key string) bool {
	if IsProviderKey(key) {
		return true
	}
	u := strings.ToUpper(key)
	for _, n := range []string{"API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE_KEY"} {
		if strings.Contains(u, n) {
			return true
		}
	}
	return false
}

// Doctor audits definitions, conflicts, and provider validity.
func Doctor(ctx context.Context, opts DoctorOptions) (*DoctorReport, error) {
	root, err := FindRepoRoot(opts.RepoRoot)
	if err != nil {
		return nil, err
	}
	envPath := filepath.Join(root, ".env")
	envMap, err := ReadEnvFile(envPath)
	if err != nil {
		return nil, err
	}
	example, _ := ReadEnvFile(filepath.Join(root, ".env.example"))

	refs, err := ScanReferences(root)
	if err != nil {
		return nil, err
	}

	interest := map[string]struct{}{}
	for k := range refs {
		if isSecretish(k) {
			interest[k] = struct{}{}
		}
	}
	for k := range envMap {
		if isSecretish(k) {
			interest[k] = struct{}{}
		}
	}
	for k := range example {
		if isSecretish(k) {
			interest[k] = struct{}{}
		}
	}
	for _, k := range []string{"XAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"} {
		interest[k] = struct{}{}
	}

	// Cross-.env* conflicts for any key name (not only secretish).
	envFiles, _ := filepath.Glob(filepath.Join(root, ".env*"))
	byKey := map[string]map[string]string{} // key -> path -> value
	for _, p := range envFiles {
		m, err := ReadEnvFile(p)
		if err != nil {
			continue
		}
		rel, _ := filepath.Rel(root, p)
		for k, v := range m {
			if byKey[k] == nil {
				byKey[k] = map[string]string{}
			}
			byKey[k][rel] = v
		}
	}
	for k, locs := range byKey {
		uniq := map[string]struct{}{}
		for _, v := range locs {
			uniq[v] = struct{}{}
		}
		if len(uniq) > 1 {
			interest[k] = struct{}{}
		}
	}

	keys := make([]string, 0, len(interest))
	for k := range interest {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	rep := &DoctorReport{}
	validator := opts.Validator
	if validator == nil {
		validator = ValidateProviderKey
	}

	for _, key := range keys {
		kr := KeyReport{Key: key, Status: "pass"}
		defs, err := ScanDefinitions(root, key)
		if err != nil {
			return nil, err
		}
		val, inEnv := envMap[key]
		_, referenced := refs[key]

		// Conflicts: env files + compose defaults always; code fallbacks for secretish keys.
		values := map[string][]string{}
		for _, d := range defs {
			if d.Value == "" {
				continue
			}
			switch d.Kind {
			case "env_file", "compose_default":
				values[d.Value] = append(values[d.Value], fmtLoc(d))
			case "go_fallback", "python_fallback":
				if isSecretish(key) {
					values[d.Value] = append(values[d.Value], fmtLoc(d))
				}
			}
		}
		if len(values) > 1 {
			kr.Status = "fail"
			var parts []string
			for v, locs := range values {
				parts = append(parts, fmt.Sprintf("%q at %s", redact(v), strings.Join(locs, ", ")))
			}
			sort.Strings(parts)
			kr.Conflicts = parts
			kr.Detail = "defined in multiple places with different values"
		}

		if referenced && len(defs) == 0 && !inEnv {
			kr.Missing = true
			kr.Status = "fail"
			kr.Detail = "referenced in code but not defined anywhere"
		}

		if IsProviderKey(key) && !opts.SkipValidate {
			if !inEnv || val == "" {
				if kr.Status == "pass" {
					kr.Status = "warn"
				}
				if kr.Detail == "" {
					kr.Detail = "provider key not set in .env"
				}
				v := ValidationResult{Key: key, OK: false, Message: "missing"}
				kr.Validation = &v
			} else {
				v := validator(ctx, key, val, envMap)
				kr.Validation = &v
				if !v.OK {
					kr.Status = "fail"
					kr.Detail = v.Message
				}
			}
		} else if IsProviderKey(key) && (!inEnv || val == "") {
			if kr.Status == "pass" {
				kr.Status = "warn"
			}
			if kr.Detail == "" {
				kr.Detail = "provider key not set in .env"
			}
		}

		// Drop uneventful rows.
		if kr.Status == "pass" && !kr.Missing && len(kr.Conflicts) == 0 {
			if !isSecretish(key) {
				continue
			}
			if opts.SkipValidate {
				kr.Detail = "set in .env (live validation skipped)"
			} else if !inEnv || val == "" {
				continue
			}
		}

		rep.Keys = append(rep.Keys, kr)
	}
	return rep, nil
}

// PrintDoctorReport writes the consolidated audit.
func PrintDoctorReport(w io.Writer, rep *DoctorReport) {
	if w == nil || rep == nil {
		return
	}
	fmt.Fprintln(w, "argusctl secrets doctor")
	fmt.Fprintln(w, strings.Repeat("─", 72))
	pass, fail, warn := 0, 0, 0
	for _, k := range rep.Keys {
		switch k.Status {
		case "pass":
			pass++
		case "fail":
			fail++
		case "warn":
			warn++
		}
		icon := "PASS"
		switch k.Status {
		case "fail":
			icon = "FAIL"
		case "warn":
			icon = "WARN"
		}
		fmt.Fprintf(w, "[%s] %s\n", icon, k.Key)
		if k.Detail != "" {
			fmt.Fprintf(w, "       %s\n", k.Detail)
		}
		for _, c := range k.Conflicts {
			fmt.Fprintf(w, "       conflict: %s\n", c)
		}
		if k.Validation != nil && k.Validation.Message != "" && k.Detail != k.Validation.Message {
			fmt.Fprintf(w, "       validate: %s\n", k.Validation.Message)
		}
	}
	fmt.Fprintln(w, strings.Repeat("─", 72))
	fmt.Fprintf(w, "summary: %d pass, %d warn, %d fail\n", pass, warn, fail)
}
