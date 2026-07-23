"""Fleet dispatcher toy service — third-party integration proof for argus-sdk.

Consumes the api-gateway (list open incidents) and ingests a few synthetic
TelemetryEvent records via IngestClient.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

from argus_sdk import (
    ArgusClient,
    DeviceType,
    IngestClient,
    SensorStatus,
    TelemetryEvent,
)


def synthesize(vehicle_id: str, trip_id: str) -> TelemetryEvent:
    return TelemetryEvent(
        vehicle_id=vehicle_id,
        trip_id=trip_id,
        timestamp=datetime.now(tz=timezone.utc),
        gps_lat=37.7749,
        gps_lon=-122.4194,
        speed_mph=22.5,
        brake_pressure=0.1,
        lidar_temp_c=42.0,
        compute_load_pct=35.0,
        sensor_status=SensorStatus.OK,
        hardware_version="dispatcher-demo",
        device_type=DeviceType.SIMULATOR,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGUS fleet-dispatcher example")
    parser.add_argument("--events", type=int, default=3, help="Synthetic events to ingest")
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Only query the gateway (no Kafka)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ARGUS_API_KEY", "demo-operator")
    with ArgusClient(api_key=api_key) as client:
        print("ping:", client.ping())
        open_incidents = client.list_incidents(status="open")
        print(f"open incidents: {len(open_incidents)}")
        for inc in open_incidents[:5]:
            print(f"  - {inc.incident_id} vehicle={inc.vehicle_id} status={inc.status}")

    if args.skip_ingest:
        return

    print(f"ingesting {args.events} synthetic event(s)…")
    with IngestClient() as ingest:
        for i in range(args.events):
            event = synthesize("VH-0004242", f"dispatcher-{int(time.time())}-{i}")
            ingest.publish(event)
            print(f"  published {event.vehicle_id} trip={event.trip_id}")
    print("done")


if __name__ == "__main__":
    main()
