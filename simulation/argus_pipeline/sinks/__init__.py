"""Built-in sinks (Iceberg via lakehouse writer patterns)."""

from argus_pipeline.sinks.scenario_ground_truth import ScenarioGroundTruthSink
from argus_pipeline.sinks.synthetic_sensor_data import SyntheticSensorDataSink
from argus_pipeline.sinks.transform_interface import TransformInterfaceSink

__all__ = [
    "ScenarioGroundTruthSink",
    "SyntheticSensorDataSink",
    "TransformInterfaceSink",
]
