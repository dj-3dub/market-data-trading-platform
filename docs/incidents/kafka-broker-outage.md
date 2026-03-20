# Incident: Kafka Broker Outage

## Summary
This scenario simulates a Kafka broker outage affecting market data distribution between the publisher and downstream consumers. The purpose is to validate detection, triage workflow, service dependency awareness, and recovery procedures in a trading-style event-driven environment.

## Impact
- Affected services: market data publisher, strategy engine, API gateway
- Impact: downstream services may stop receiving fresh data or process stale inputs
- Severity: High
- Scenario type: simulated failure

## Detection
Expected detection methods:
- Kafka container unhealthy or stopped
- Consumer lag increases
- Strategy engine metrics stop updating
- API begins serving stale or incomplete data
- Grafana dashboards show flatlined throughput

## Symptoms
- No fresh messages on event stream
- Consumer services appear up but data stops moving
- Strategy decisions become stale
- Metrics remain static despite system uptime

## Initial Hypotheses
- Kafka container stopped
- Docker network communication issue
- Broker port unavailable
- Producer unable to publish
- Consumer unable to connect

## Investigation Steps
1. Check running containers
2. Review Kafka logs
3. Validate broker port exposure
4. Confirm producer connectivity
5. Confirm consumer connectivity
6. Review Prometheus metrics for throughput and lag

## Root Cause
Placeholder for homelab validation.

## Resolution
Placeholder for homelab validation.

## Recovery Validation
- Kafka broker healthy
- Producer resumes publishing
- Consumer lag returns to normal
- Strategy metrics update again
- Dashboards show message flow restored

## Preventive Actions
- Add broker health checks
- Add lag-based alerting
- Add synthetic publish/consume validation
- Improve recovery runbook

## Commands / Evidence
Add later from homelab:
```bash
docker ps
docker logs kafka
ss -tulpn
docker exec -it <container> sh
