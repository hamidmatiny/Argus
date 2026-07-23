package upstream

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/hamba/avro/v2"
	"github.com/segmentio/kafka-go"
	argusv1 "github.com/argus-platform/argus/shared/gen/go/argus/v1"
)

// TelemetryStreamer consumes validated telemetry from Kafka.
type TelemetryStreamer struct {
	Brokers           []string
	Topic             string
	GroupID           string
	SchemaRegistryURL string
	Dialer            *kafka.Dialer
}

// StreamFunc is invoked for each decoded event until it returns an error or ctx ends.
type StreamFunc func(*argusv1.TelemetryEvent) error

// Stream reads from Kafka and invokes fn for matching events.
func (s *TelemetryStreamer) Stream(ctx context.Context, vehicleID string, fn StreamFunc) error {
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:        s.Brokers,
		Topic:          s.Topic,
		GroupID:        s.GroupID + "-" + fmt.Sprint(time.Now().UnixNano()%1_000_000),
		MinBytes:       1,
		MaxBytes:       10e6,
		MaxWait:        500 * time.Millisecond,
		StartOffset:    kafka.LastOffset,
		Dialer:         s.Dialer,
		CommitInterval: time.Second,
	})
	defer reader.Close()

	schemaCache := map[int]avro.Schema{}
	for {
		msg, err := reader.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		ev, err := decodeTelemetry(msg.Value, s.SchemaRegistryURL, schemaCache)
		if err != nil {
			slog.Warn("telemetry_decode_failed", "err", err)
			continue
		}
		if vehicleID != "" && ev.VehicleId != vehicleID {
			continue
		}
		if err := fn(ev); err != nil {
			return err
		}
	}
}

func decodeTelemetry(raw []byte, registry string, cache map[int]avro.Schema) (*argusv1.TelemetryEvent, error) {
	if len(raw) == 0 {
		return nil, fmt.Errorf("empty message")
	}
	// Prefer JSON (tests / some emitters).
	if raw[0] == '{' {
		var m map[string]any
		if err := json.Unmarshal(raw, &m); err != nil {
			return nil, err
		}
		return mapToEvent(m), nil
	}
	// Confluent wire format: 0x00 + 4-byte schema id + avro payload.
	if len(raw) > 5 && raw[0] == 0 {
		id := int(binary.BigEndian.Uint32(raw[1:5]))
		schema, ok := cache[id]
		if !ok {
			s, err := fetchSchema(registry, id)
			if err != nil {
				return nil, err
			}
			schema = s
			cache[id] = schema
		}
		var m map[string]any
		if err := avro.Unmarshal(schema, raw[5:], &m); err != nil {
			return nil, err
		}
		return mapToEvent(m), nil
	}
	return nil, fmt.Errorf("unsupported payload encoding")
}

func fetchSchema(registry string, id int) (avro.Schema, error) {
	if registry == "" {
		return nil, fmt.Errorf("schema registry URL unset")
	}
	url := strings.TrimRight(registry, "/") + fmt.Sprintf("/schemas/ids/%d", id)
	resp, err := http.Get(url) //nolint:gosec // local registry
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("schema registry status %d", resp.StatusCode)
	}
	var payload struct {
		Schema string `json:"schema"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, err
	}
	return avro.Parse(payload.Schema)
}

func mapToEvent(m map[string]any) *argusv1.TelemetryEvent {
	ev := &argusv1.TelemetryEvent{
		VehicleId:      asString(m["vehicle_id"]),
		TripId:         asString(m["trip_id"]),
		Timestamp:      asString(m["timestamp"]),
		GpsLat:         asFloat(m["gps_lat"]),
		GpsLon:         asFloat(m["gps_lon"]),
		SpeedMph:       asFloat(m["speed_mph"]),
		BrakePressure:  asFloat(m["brake_pressure"]),
		LidarTempC:     asFloat(m["lidar_temp_c"]),
		ComputeLoadPct: asFloat(m["compute_load_pct"]),
		HardwareVersion: asString(m["hardware_version"]),
	}
	switch strings.ToUpper(asString(m["sensor_status"])) {
	case "OK", "SENSOR_STATUS_OK":
		ev.SensorStatus = argusv1.SensorStatus_SENSOR_STATUS_OK
	case "DEGRADED", "SENSOR_STATUS_DEGRADED":
		ev.SensorStatus = argusv1.SensorStatus_SENSOR_STATUS_DEGRADED
	case "FAULT", "SENSOR_STATUS_FAULT":
		ev.SensorStatus = argusv1.SensorStatus_SENSOR_STATUS_FAULT
	}
	switch strings.ToUpper(asString(m["device_type"])) {
	case "VEHICLE", "DEVICE_TYPE_VEHICLE":
		ev.DeviceType = argusv1.DeviceType_DEVICE_TYPE_VEHICLE
	case "SIMULATOR", "DEVICE_TYPE_SIMULATOR":
		ev.DeviceType = argusv1.DeviceType_DEVICE_TYPE_SIMULATOR
	case "EDGE_GATEWAY", "DEVICE_TYPE_EDGE_GATEWAY":
		ev.DeviceType = argusv1.DeviceType_DEVICE_TYPE_EDGE_GATEWAY
	}
	return ev
}

func asString(v any) string {
	switch t := v.(type) {
	case string:
		return t
	case fmt.Stringer:
		return t.String()
	default:
		if v == nil {
			return ""
		}
		return fmt.Sprint(v)
	}
}

func asFloat(v any) float64 {
	switch t := v.(type) {
	case float64:
		return t
	case float32:
		return float64(t)
	case int:
		return float64(t)
	case int64:
		return float64(t)
	case json.Number:
		f, _ := t.Float64()
		return f
	default:
		return 0
	}
}
