package upstream

import (
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

// IncidentsClient talks to incident-engine REST.
type IncidentsClient struct {
	BaseURL string
	Client  *http.Client
}

// Incident is a subset of incident-engine's IncidentRecord.
type Incident struct {
	IncidentID    string `json:"incident_id"`
	VehicleID     string `json:"vehicle_id"`
	Severity      string `json:"severity"`
	Status        string `json:"status"`
	SourceService string `json:"source_service"`
	Timestamp     string `json:"timestamp"`
	Summary       string `json:"summary"`
	Open          bool   `json:"open"`
}

// List returns incidents, optionally filtered by status.
func (c *IncidentsClient) List(ctx context.Context, status string) ([]Incident, error) {
	u := strings.TrimRight(c.BaseURL, "/") + "/incidents"
	if status != "" {
		u += "?status=" + url.QueryEscape(status)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, err
	}
	var out struct {
		Incidents []Incident `json:"incidents"`
	}
	if err := c.doJSON(req, &out); err != nil {
		return nil, err
	}
	return out.Incidents, nil
}

// Acknowledge marks an incident acknowledged.
func (c *IncidentsClient) Acknowledge(ctx context.Context, id, note string) (*Incident, error) {
	body, _ := json.Marshal(map[string]string{"note": note})
	u := strings.TrimRight(c.BaseURL, "/") + "/incidents/" + url.PathEscape(id) + "/acknowledge"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	var out struct {
		Incident Incident `json:"incident"`
	}
	if err := c.doJSON(req, &out); err != nil {
		return nil, err
	}
	return &out.Incident, nil
}

func (c *IncidentsClient) doJSON(req *http.Request, dest any) error {
	client := c.Client
	if client == nil {
		client = &http.Client{Timeout: 15 * time.Second}
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		return fmt.Errorf("incident-engine status %d: %s", resp.StatusCode, string(b))
	}
	return json.Unmarshal(b, dest)
}
