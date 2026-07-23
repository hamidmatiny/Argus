# Quarantine rate spike

## Symptoms

- QA pass ratio SLO drops below 99% (Grafana / Prometheus `argus:qa_pass_ratio`)
- lakehouse `fleet.quarantine` row count climbs
- stream-processor logs show elevated `qa_reject` reasons

## Likely causes

1. Simulator `failure-rate` too high in local demos
2. Schema / contract drift (new enum, bad GPS bounds)
3. Downstream clock skew producing invalid timestamps

## Investigation steps

1. Check stream-processor `/health` stats
2. Query quarantine via gateway (scoped SQL only):
   `SELECT reason, count(*) FROM quarantine GROUP BY 1 ORDER BY 2 DESC LIMIT 20`
3. Spot-check rejected payloads in Kafka topic `telemetry.quarantine` if needed
4. Compare against recent deploy of stream-processor or shared contracts

## Mitigation

- Fix producer / simulator config; do not widen QA gates without review
- Re-drive clean traffic and watch `argus:qa_pass_ratio` recover
- Page on-call only if production quarantine rate stays elevated >15m

## Citations

- Phase 3 stream-processor QA gate
- Lakehouse quarantine table docs
