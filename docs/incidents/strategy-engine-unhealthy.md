# Incident: Strategy Engine Unhealthy

## Summary
This scenario simulates the strategy engine becoming unhealthy, unresponsive, or logically degraded while upstream data ingestion may still appear normal.

## Impact
- Affected services: strategy engine, API gateway, metrics consumers
- Impact: stale or missing strategy outputs despite continued market data flow
- Severity: High
- Scenario type: simulated application failure

## Detection
Expected detection methods:
- Health endpoint failure
- Missing or stale strategy metrics
- Increased restart count
- Logs showing exceptions or processing stalls

## Symptoms
- Strategy outputs stop updating
- Health checks fail or become intermittent
- Market data continues but downstream decisions do not
- Grafana shows asymmetry between ingestion and processing

## Initial Hypotheses
- Application crash
- Dependency issue
- Bad input handling
- Resource starvation
- Kafka consumer fault

## Investigation Steps
1. Check container status and restart count
2. Review application logs
3. Validate health endpoint
4. Confirm inbound stream presence
5. Compare input rate vs processed rate
6. Restart service if needed and validate recovery

## Root Cause
Placeholder for homelab validation.

## Resolution
Placeholder for homelab validation.

## Recovery Validation
- Strategy engine healthy
- Processing resumes
- Metrics are fresh
- No sustained backlog remains

## Preventive Actions
- Better liveness and readiness checks
- Add error-rate dashboard
- Add stalled-processing alert
- Improve dependency validation on startup

## Commands / Evidence
Add later from homelab:
```bash
docker ps
docker logs <strategy-container>
curl http://localhost:<port>/health
