# Trip when drifted feature count meets the multi-feature threshold.
package argus.incident

default trip_drift = false

trip_drift {
	input.drifted_feature_count >= input.drift_min_features
}

reason_drift = sprintf(
	"multi_feature_drift: count=%d threshold=%d",
	[input.drifted_feature_count, input.drift_min_features],
) {
	trip_drift
}
