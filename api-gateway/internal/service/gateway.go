package service

import (
	"context"
	"fmt"
	"strings"

	"github.com/argus-platform/argus/api-gateway/internal/upstream"
	argusv1 "github.com/argus-platform/argus/shared/gen/go/argus/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
)

// Gateway implements argusv1.GatewayServiceServer.
type Gateway struct {
	argusv1.UnimplementedGatewayServiceServer
	Trino     *upstream.TrinoClient
	Incidents *upstream.IncidentsClient
	Dagster   *upstream.DagsterClient
	Stream    *upstream.TelemetryStreamer
}

func (g *Gateway) QueryTelemetry(ctx context.Context, req *argusv1.QueryTelemetryRequest) (*argusv1.QueryTelemetryResponse, error) {
	res, err := g.Trino.Query(ctx, req.GetSql(), req.GetLimit())
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "trino: %v", err)
	}
	rows := make([]*structpb.Struct, 0, len(res.Rows))
	for _, row := range res.Rows {
		st, err := structpb.NewStruct(row)
		if err != nil {
			// Best-effort stringify non-JSON-friendly values.
			clean := map[string]any{}
			for k, v := range row {
				clean[k] = fmt.Sprint(v)
			}
			st, err = structpb.NewStruct(clean)
			if err != nil {
				continue
			}
		}
		rows = append(rows, st)
	}
	return &argusv1.QueryTelemetryResponse{
		Columns:  res.Columns,
		Rows:     rows,
		RowCount: int32(res.RowCount),
	}, nil
}

func (g *Gateway) ListIncidents(ctx context.Context, req *argusv1.ListIncidentsRequest) (*argusv1.ListIncidentsResponse, error) {
	items, err := g.Incidents.List(ctx, req.GetStatus())
	if err != nil {
		return nil, status.Errorf(codes.Unavailable, "incident-engine: %v", err)
	}
	out := make([]*argusv1.IncidentSummary, 0, len(items))
	for _, it := range items {
		out = append(out, toSummary(it))
	}
	return &argusv1.ListIncidentsResponse{Incidents: out}, nil
}

func (g *Gateway) AcknowledgeIncident(ctx context.Context, req *argusv1.AcknowledgeIncidentRequest) (*argusv1.AcknowledgeIncidentResponse, error) {
	if req.GetIncidentId() == "" {
		return nil, status.Error(codes.InvalidArgument, "incident_id required")
	}
	it, err := g.Incidents.Acknowledge(ctx, req.GetIncidentId(), req.GetNote())
	if err != nil {
		if strings.Contains(err.Error(), "404") || strings.Contains(err.Error(), "not found") {
			return nil, status.Errorf(codes.NotFound, "%v", err)
		}
		return nil, status.Errorf(codes.Unavailable, "incident-engine: %v", err)
	}
	return &argusv1.AcknowledgeIncidentResponse{Incident: toSummary(*it)}, nil
}

func (g *Gateway) TriggerRetraining(ctx context.Context, req *argusv1.TriggerRetrainingRequest) (*argusv1.TriggerRetrainingResponse, error) {
	res, err := g.Dagster.TriggerRetraining(ctx, req.GetReason(), req.GetTags())
	if err != nil {
		return &argusv1.TriggerRetrainingResponse{
			Status:  "error",
			Message: err.Error(),
		}, status.Errorf(codes.Unavailable, "dagster: %v", err)
	}
	return &argusv1.TriggerRetrainingResponse{
		RunId:   res.RunID,
		Status:  res.Status,
		Message: res.Message,
	}, nil
}

func (g *Gateway) StreamTelemetry(req *argusv1.StreamTelemetryRequest, stream argusv1.GatewayService_StreamTelemetryServer) error {
	if g.Stream == nil {
		return status.Error(codes.Unavailable, "stream not configured")
	}
	return g.Stream.Stream(stream.Context(), req.GetVehicleId(), func(ev *argusv1.TelemetryEvent) error {
		return stream.Send(&argusv1.StreamTelemetryResponse{Event: ev})
	})
}

func toSummary(it upstream.Incident) *argusv1.IncidentSummary {
	return &argusv1.IncidentSummary{
		IncidentId:    it.IncidentID,
		VehicleId:     it.VehicleID,
		Severity:      mapSeverity(it.Severity),
		Status:        mapStatus(it.Status),
		SourceService: it.SourceService,
		Timestamp:     it.Timestamp,
		Reason:        it.Summary,
	}
}

func mapSeverity(s string) argusv1.IncidentSeverity {
	switch strings.ToLower(s) {
	case "critical":
		return argusv1.IncidentSeverity_INCIDENT_SEVERITY_CRITICAL
	case "warning":
		return argusv1.IncidentSeverity_INCIDENT_SEVERITY_WARNING
	case "info":
		return argusv1.IncidentSeverity_INCIDENT_SEVERITY_INFO
	default:
		return argusv1.IncidentSeverity_INCIDENT_SEVERITY_UNSPECIFIED
	}
}

func mapStatus(s string) argusv1.IncidentStatus {
	switch strings.ToLower(s) {
	case "open":
		return argusv1.IncidentStatus_INCIDENT_STATUS_OPEN
	case "acknowledged":
		return argusv1.IncidentStatus_INCIDENT_STATUS_ACKNOWLEDGED
	case "resolved":
		return argusv1.IncidentStatus_INCIDENT_STATUS_RESOLVED
	default:
		return argusv1.IncidentStatus_INCIDENT_STATUS_UNSPECIFIED
	}
}
