# Future Homelab Test Plan

When homelab access is available again, this project will be extended with live validation and failure simulation.

## Planned Hands-On Work
- Capture command output for troubleshooting guide
- Record Grafana screenshots
- Measure endpoint latency under load
- Test Kafka outage and recovery
- Validate consumer lag scenarios
- Add packet capture examples where appropriate

## Evidence to Collect
- `docker ps`
- `docker logs`
- `ss -tulpn`
- `curl` timing output
- dashboard screenshots
- incident timelines
- recovery notes

## Goal
Convert this project from a design-and-documentation portfolio piece into a fully demonstrated reliability engineering lab.
