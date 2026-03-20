# Incident: API Gateway Latency Spike

## Summary
This scenario simulates elevated latency at the FastAPI gateway, affecting responsiveness for external consumers and obscuring whether the issue originates in the gateway itself or in a downstream dependency.

## Impact
- Affected services: API gateway, downstream services, dashboard consumers
- Impact: slow reads, delayed responses, degraded visibility into platform state
- Severity: Medium to High
- Scenario type: simulated degradation

## Detection
Expected detection methods:
- Increased response time metrics
- Grafana latency panel deviation
- Manual curl timing tests
- Elevated application log timings

## Symptoms
- Slow API responses
- Timeout risk from callers
- Increased queueing or retry behavior
- Normal container uptime despite degraded performance

## Initial Hypotheses
- FastAPI process slowdown
- Dependency latency from strategy engine
- Kafka backlog affecting freshness
- Resource contention in container
- DNS or Docker network delay

## Investigation Steps
1. Measure endpoint latency with curl
2. Check container resource consumption
3. Review gateway logs
4. Compare downstream service health
5. Validate Docker networking path
6. Review recent restart or deploy events

## Root Cause
Placeholder for homelab validation.

## Resolution
Placeholder for homelab validation.

## Recovery Validation
- Endpoint latency returns to baseline
- No timeout behavior observed
- Metrics and dashboard freshness restored

## Preventive Actions
- Add latency threshold alerts
- Add dependency timing breakdown
- Add synthetic endpoint checks
- Add resource utilization visibility

## Commands / Evidence
Add later from homelab:
```bash
curl -w "\nlookup:%{time_namelookup} connect:%{time_connect} starttransfer:%{time_starttransfer} total:%{time_total}\n" http://localhost:<port>/health
docker stats
docker logs <gateway-container>
