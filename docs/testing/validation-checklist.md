# Validation Checklist

Run `make up`, `python3 scripts/verify-pipeline.py`, then `make doctor test`.
Run `make incident` for automated consumer-outage and recovery validation.
See [the local demo guide](../operations/demo.md) for expected results.

## Platform Baseline
- [ ] All required containers running
- [ ] Health endpoints responding
- [ ] Metrics visible in Prometheus
- [ ] Dashboards loading in Grafana
- [ ] API responds successfully
- [ ] Strategy outputs updating
- [ ] Market data flowing

## Incident Simulation Ready
- [ ] Baseline state recorded
- [ ] Relevant dashboards identified
- [ ] Logs accessible
- [ ] Recovery steps documented
- [ ] Test scope defined

## Post-Recovery Validation
- [ ] Services healthy
- [ ] Data freshness restored
- [ ] Metrics updating
- [ ] No abnormal restart loop
- [ ] Notes captured
