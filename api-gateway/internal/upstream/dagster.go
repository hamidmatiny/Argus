package upstream

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// DagsterClient launches jobs via Dagster GraphQL.
type DagsterClient struct {
	GraphQLURL    string
	LocationName  string
	RepositoryName string
	JobName       string
	Client        *http.Client
}

// LaunchResult is returned after a launchRun mutation.
type LaunchResult struct {
	RunID   string
	Status  string
	Message string
}

const launchMutation = `
mutation Launch($executionParams: ExecutionParams!) {
  launchRun(executionParams: $executionParams) {
    __typename
    ... on LaunchRunSuccess {
      run { id status }
    }
    ... on PythonError { message }
    ... on UnauthorizedError { message }
    ... on PipelineNotFoundError { message }
    ... on InvalidSubsetError { message }
    ... on RunConfigValidationInvalid { errors { message } }
  }
}`

// TriggerRetraining launches the configured Dagster job.
func (d *DagsterClient) TriggerRetraining(ctx context.Context, reason string, tags map[string]string) (*LaunchResult, error) {
	tagList := []map[string]string{
		{"key": "source", "value": "api-gateway"},
		{"key": "reason", "value": reason},
	}
	for k, v := range tags {
		tagList = append(tagList, map[string]string{"key": k, "value": v})
	}
	vars := map[string]any{
		"executionParams": map[string]any{
			"selector": map[string]any{
				"repositoryName":         d.RepositoryName,
				"repositoryLocationName": d.LocationName,
				"jobName":                d.JobName,
			},
			"executionMetadata": map[string]any{
				"tags": tagList,
			},
		},
	}
	payload := map[string]any{"query": launchMutation, "variables": vars}
	body, _ := json.Marshal(payload)
	client := d.Client
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, d.GraphQLURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("dagster status %d: %s", resp.StatusCode, string(raw))
	}
	var envelope struct {
		Data struct {
			LaunchRun map[string]any `json:"launchRun"`
		} `json:"data"`
		Errors []struct {
			Message string `json:"message"`
		} `json:"errors"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return nil, err
	}
	if len(envelope.Errors) > 0 {
		return nil, fmt.Errorf("dagster graphql: %s", envelope.Errors[0].Message)
	}
	lr := envelope.Data.LaunchRun
	if lr == nil {
		return nil, fmt.Errorf("empty launchRun response: %s", string(raw))
	}
	typename, _ := lr["__typename"].(string)
	if typename == "LaunchRunSuccess" {
		run, _ := lr["run"].(map[string]any)
		id, _ := run["id"].(string)
		status, _ := run["status"].(string)
		return &LaunchResult{RunID: id, Status: status, Message: "launched"}, nil
	}
	msg, _ := lr["message"].(string)
	if msg == "" {
		if errs, ok := lr["errors"].([]any); ok && len(errs) > 0 {
			if m, ok := errs[0].(map[string]any); ok {
				msg, _ = m["message"].(string)
			}
		}
	}
	if msg == "" {
		msg = typename
	}
	return &LaunchResult{Status: "error", Message: msg}, fmt.Errorf("launch failed: %s", msg)
}

// NormalizeGraphQLURL ensures a /graphql suffix when a base URL is provided.
func NormalizeGraphQLURL(u string) string {
	u = strings.TrimRight(u, "/")
	if strings.HasSuffix(u, "/graphql") {
		return u
	}
	return u + "/graphql"
}
