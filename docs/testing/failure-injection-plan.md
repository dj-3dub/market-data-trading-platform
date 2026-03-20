# Failure Injection Plan

This document defines the controlled failure scenarios that will be tested in the homelab.

## Planned Scenarios
- Stop Kafka broker
- Restart loop on strategy engine
- Introduce API latency
- Break service dependency order
- Disable metrics scraping
- Create stale data condition

## Test Method
For each scenario:
1. Define expected symptom
2. Trigger controlled failure
3. Observe dashboards and logs
4. Execute triage steps
5. Recover service
6. Document lessons learned

## Success Criteria
- Issue detected quickly
- Root cause identified accurately
- Recovery is repeatable
- Documentation improved after test
