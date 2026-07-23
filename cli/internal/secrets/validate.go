package secrets

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// ValidationResult is the outcome of a live provider check.
type ValidationResult struct {
	Key      string
	Provider string
	OK       bool
	Status   int
	Message  string
}

// ValidateProviderKey makes the cheapest possible live call for known providers.
func ValidateProviderKey(ctx context.Context, key, value string, env map[string]string) ValidationResult {
	if value == "" {
		return ValidationResult{Key: key, OK: false, Message: "empty value"}
	}
	client := &http.Client{Timeout: 15 * time.Second}

	switch {
	case key == "XAI_API_KEY" || strings.HasPrefix(key, "XAI_"):
		return hit(ctx, client, key, "xAI", "GET", "https://api.x.ai/v1/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	case key == "OPENAI_API_KEY" || strings.HasPrefix(key, "OPENAI_"):
		return hit(ctx, client, key, "OpenAI", "GET", "https://api.openai.com/v1/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	case key == "ANTHROPIC_API_KEY" || strings.HasPrefix(key, "ANTHROPIC_"):
		return hit(ctx, client, key, "Anthropic", "GET", "https://api.anthropic.com/v1/models", map[string]string{
			"x-api-key":         value,
			"anthropic-version": "2023-06-01",
		})
	case key == "GROQ_API_KEY" || strings.HasPrefix(key, "GROQ_"):
		return hit(ctx, client, key, "Groq", "GET", "https://api.groq.com/openai/v1/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	case key == "MISTRAL_API_KEY" || strings.HasPrefix(key, "MISTRAL_"):
		return hit(ctx, client, key, "Mistral", "GET", "https://api.mistral.ai/v1/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	case key == "COHERE_API_KEY" || strings.HasPrefix(key, "COHERE_"):
		return hit(ctx, client, key, "Cohere", "GET", "https://api.cohere.com/v1/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	case key == "GOOGLE_API_KEY" || strings.HasPrefix(key, "GEMINI_"):
		url := "https://generativelanguage.googleapis.com/v1/models?key=" + value
		return hit(ctx, client, key, "Google/Gemini", "GET", url, nil)
	case key == "LLM_API_KEY":
		base := firstNonEmpty(env["LLM_API_BASE_URL"], os.Getenv("LLM_API_BASE_URL"))
		if base == "" {
			return ValidationResult{
				Key:      key,
				Provider: "LLM",
				OK:       false,
				Message:  "LLM_API_KEY set but LLM_API_BASE_URL is empty — cannot live-validate",
			}
		}
		base = strings.TrimRight(base, "/")
		return hit(ctx, client, key, "LLM", "GET", base+"/models", map[string]string{
			"Authorization": "Bearer " + value,
		})
	default:
		return ValidationResult{
			Key:     key,
			OK:      true,
			Message: "not a known provider key — skipped live validation",
		}
	}
}

func hit(ctx context.Context, client *http.Client, key, provider, method, url string, headers map[string]string) ValidationResult {
	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		return ValidationResult{Key: key, Provider: provider, OK: false, Message: err.Error()}
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		return ValidationResult{
			Key:      key,
			Provider: provider,
			OK:       false,
			Message:  fmt.Sprintf("%s request failed: %v", provider, err),
		}
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
	res := ValidationResult{Key: key, Provider: provider, Status: resp.StatusCode}
	switch {
	case resp.StatusCode == 401 || resp.StatusCode == 403:
		res.OK = false
		res.Message = fmt.Sprintf("%s rejected by provider (%d)", key, resp.StatusCode)
		if snippet := compactAPIError(body); snippet != "" {
			res.Message += ": " + snippet
		}
	case resp.StatusCode == 400:
		// xAI and others often return 400 for malformed/invalid API keys.
		res.OK = false
		res.Message = fmt.Sprintf("%s rejected by provider (400)", key)
		if snippet := compactAPIError(body); snippet != "" {
			res.Message += ": " + snippet
		}
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		res.OK = true
		res.Message = fmt.Sprintf("%s accepted by %s (%d)", key, provider, resp.StatusCode)
	case resp.StatusCode == 404:
		// Some providers use different list paths; 404 with auth often still means key was parsed.
		res.OK = false
		res.Message = fmt.Sprintf("%s got HTTP %d from %s (endpoint may differ; treat as validation failure)", key, resp.StatusCode, provider)
	default:
		res.OK = false
		res.Message = fmt.Sprintf("%s unexpected HTTP %d from %s", key, resp.StatusCode, provider)
		if snippet := compactAPIError(body); snippet != "" {
			res.Message += ": " + snippet
		}
	}
	return res
}

func compactAPIError(body []byte) string {
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		s := strings.TrimSpace(string(body))
		if len(s) > 120 {
			s = s[:120] + "…"
		}
		return s
	}
	if errObj, ok := m["error"].(map[string]any); ok {
		if msg, ok := errObj["message"].(string); ok {
			return msg
		}
	}
	if msg, ok := m["message"].(string); ok {
		return msg
	}
	return ""
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
