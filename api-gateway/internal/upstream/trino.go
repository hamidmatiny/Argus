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

// TrinoClient runs SELECT statements via Trino's HTTP API.
type TrinoClient struct {
	BaseURL string
	User    string
	Catalog string
	Schema  string
	Client  *http.Client
}

// QueryResult is a simplified tabular response.
type QueryResult struct {
	Columns  []string
	Rows     []map[string]any
	RowCount int
}

// Query executes sql (SELECT-only) and materializes rows.
func (t *TrinoClient) Query(ctx context.Context, sql string, limit int32) (*QueryResult, error) {
	sql = strings.TrimSpace(sql)
	if sql == "" {
		sql = fmt.Sprintf("SELECT * FROM %s.%s.telemetry LIMIT 20", t.Catalog, t.Schema)
	}
	upper := strings.ToUpper(sql)
	if !strings.HasPrefix(upper, "SELECT") && !strings.HasPrefix(upper, "SHOW") && !strings.HasPrefix(upper, "DESCRIBE") {
		return nil, fmt.Errorf("only SELECT/SHOW/DESCRIBE statements are allowed")
	}
	if limit > 0 && !strings.Contains(upper, " LIMIT ") {
		sql = fmt.Sprintf("%s LIMIT %d", sql, limit)
	}
	client := t.Client
	if client == nil {
		client = &http.Client{Timeout: 60 * time.Second}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(t.BaseURL, "/")+"/v1/statement", bytes.NewBufferString(sql))
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Trino-User", t.User)
	req.Header.Set("X-Trino-Catalog", t.Catalog)
	req.Header.Set("X-Trino-Schema", t.Schema)
	req.Header.Set("Content-Type", "text/plain")

	var columns []string
	var rows []map[string]any
	next := req
	for next != nil {
		resp, err := client.Do(next)
		if err != nil {
			return nil, err
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, err
		}
		if resp.StatusCode >= 300 {
			return nil, fmt.Errorf("trino status %d: %s", resp.StatusCode, string(body))
		}
		var page trinoPage
		if err := json.Unmarshal(body, &page); err != nil {
			return nil, err
		}
		if page.Error != nil {
			return nil, fmt.Errorf("trino error: %s", page.Error.Message)
		}
		if len(columns) == 0 {
			for _, c := range page.Columns {
				columns = append(columns, c.Name)
			}
		}
		for _, data := range page.Data {
			row := map[string]any{}
			for i, col := range columns {
				if i < len(data) {
					row[col] = data[i]
				}
			}
			rows = append(rows, row)
		}
		if page.NextURI == "" {
			break
		}
		next, err = http.NewRequestWithContext(ctx, http.MethodGet, page.NextURI, nil)
		if err != nil {
			return nil, err
		}
		next.Header.Set("X-Trino-User", t.User)
	}
	return &QueryResult{Columns: columns, Rows: rows, RowCount: len(rows)}, nil
}

type trinoPage struct {
	NextURI string `json:"nextUri"`
	Columns []struct {
		Name string `json:"name"`
	} `json:"columns"`
	Data  [][]any `json:"data"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}
