package gateway

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client talks to the ARGUS api-gateway REST surface.
type Client struct {
	BaseURL    string
	APIKey     string
	Token      string
	HTTPClient *http.Client
}

func (c *Client) http() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return &http.Client{Timeout: 30 * time.Second}
}

func (c *Client) base() string {
	return strings.TrimRight(c.BaseURL, "/")
}

func (c *Client) do(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.base()+path, rdr)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	} else if c.APIKey != "" {
		req.Header.Set("X-API-Key", c.APIKey)
	}
	return c.http().Do(req)
}

func (c *Client) decodeError(res *http.Response) error {
	b, _ := io.ReadAll(io.LimitReader(res.Body, 4096))
	msg := strings.TrimSpace(string(b))
	if msg == "" {
		msg = res.Status
	}
	return fmt.Errorf("gateway %s: %s", res.Status, msg)
}

// Incident is a gateway incident summary (snake_case JSON).
type Incident struct {
	IncidentID    string `json:"incident_id"`
	VehicleID     string `json:"vehicle_id"`
	Severity      string `json:"severity"`
	Status        string `json:"status"`
	SourceService string `json:"source_service"`
	Timestamp     string `json:"timestamp"`
	Reason        string `json:"reason"`
}

type listIncidentsResp struct {
	Incidents []Incident `json:"incidents"`
}

func (c *Client) ListIncidents(ctx context.Context, status string) ([]Incident, error) {
	path := "/v1/incidents"
	if status != "" {
		path += "?status=" + url.QueryEscape(status)
	}
	res, err := c.do(ctx, http.MethodGet, path, nil)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return nil, c.decodeError(res)
	}
	var out listIncidentsResp
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out.Incidents, nil
}

func (c *Client) Acknowledge(ctx context.Context, id, note string) (*Incident, error) {
	res, err := c.do(ctx, http.MethodPost, "/v1/incidents/"+url.PathEscape(id)+"/acknowledge", map[string]string{"note": note})
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return nil, c.decodeError(res)
	}
	var wrap struct {
		Incident Incident `json:"incident"`
	}
	if err := json.NewDecoder(res.Body).Decode(&wrap); err != nil {
		return nil, err
	}
	return &wrap.Incident, nil
}

type RetrainResponse struct {
	RunID   string `json:"run_id"`
	Status  string `json:"status"`
	Message string `json:"message"`
}

func (c *Client) TriggerRetrain(ctx context.Context, reason string) (*RetrainResponse, error) {
	res, err := c.do(ctx, http.MethodPost, "/v1/retraining:trigger", map[string]any{
		"reason": reason,
		"tags":   map[string]string{},
	})
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return nil, c.decodeError(res)
	}
	var out RetrainResponse
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StreamTelemetry reads NDJSON lines until ctx cancel or EOF.
func (c *Client) StreamTelemetry(ctx context.Context, vehicleID string, fn func(line []byte) error) error {
	path := "/v1/telemetry/stream"
	if vehicleID != "" {
		path += "?vehicle_id=" + url.QueryEscape(vehicleID)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base()+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	} else if c.APIKey != "" {
		req.Header.Set("X-API-Key", c.APIKey)
	}
	// No overall timeout for streaming; rely on context.
	httpClient := &http.Client{}
	res, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return c.decodeError(res)
	}
	sc := bufio.NewScanner(res.Body)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for sc.Scan() {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		line := bytes.TrimSpace(sc.Bytes())
		if len(line) == 0 {
			continue
		}
		// Copy because Scanner reuses buffer.
		cp := append([]byte(nil), line...)
		if err := fn(cp); err != nil {
			return err
		}
	}
	return sc.Err()
}

func (c *Client) Ping(ctx context.Context) error {
	res, err := c.do(ctx, http.MethodGet, "/v1/ping", nil)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	if res.StatusCode >= 400 {
		return c.decodeError(res)
	}
	return nil
}
