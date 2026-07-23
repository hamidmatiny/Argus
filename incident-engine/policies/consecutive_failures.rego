# Trip when QA rate has exceeded its threshold for N consecutive batches.
package argus.incident

default trip_consecutive = false

trip_consecutive {
	input.consecutive_failures >= input.consecutive_failure_max
}

reason_consecutive = sprintf(
	"consecutive_qa_failures: count=%d threshold=%d",
	[input.consecutive_failures, input.consecutive_failure_max],
) {
	trip_consecutive
}
