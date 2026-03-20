# Incident Template

## Incident Title
Short, specific summary of the failure.

## Summary
Describe what happened in 2-4 sentences.

## Impact
- Affected services:
- User/business impact:
- Severity:
- Start time:
- End time:
- Duration:

## Detection
How was the issue identified?
- Alert
- Dashboard
- Manual observation
- Log review
- Synthetic check

## Symptoms
List the observable symptoms.
- Example: API returning 5xx
- Example: Kafka consumer lag rising
- Example: Strategy engine metrics stale

## Initial Hypotheses
What did you suspect first?

## Investigation Steps
Document the order of operations.
1. Checked container health
2. Reviewed logs
3. Verified port bindings
4. Confirmed Kafka broker status
5. Reviewed metrics and latency trends

## Root Cause
What actually caused the issue?

## Resolution
What fixed it?

## Recovery Validation
How did you confirm normal operation returned?

## Preventive Actions
What should be added or changed to reduce recurrence?
- Alerting
- Retry logic
- Dependency checks
- Health checks
- Better dashboards
- Runbook updates

## Commands / Evidence
Add commands, screenshots, or log samples here later.
