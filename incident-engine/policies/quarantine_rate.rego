# Trip when rolling quarantine rate exceeds threshold over a full QA window.
package argus.incident

default trip_quarantine = false

trip_quarantine {
	input.qa_batch_count >= input.qa_window_batches
	input.rolling_quarantine_rate > input.qa_rate_threshold
}

reason_quarantine = sprintf(
	"qa_quarantine_rate_exceeded: rolling=%.4f threshold=%.4f batches=%d",
	[input.rolling_quarantine_rate, input.qa_rate_threshold, input.qa_batch_count],
) {
	trip_quarantine
}
