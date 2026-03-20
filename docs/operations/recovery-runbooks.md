# Recovery Runbooks

## Kafka Service Recovery
1. Confirm broker container state
2. Review Kafka logs
3. Validate port and network path
4. Restart service if appropriate
5. Confirm producer/consumer recovery
6. Validate metrics and freshness

## API Gateway Recovery
1. Confirm gateway container state
2. Check health endpoint
3. Measure latency manually
4. Inspect downstream dependency status
5. Restart if required
6. Confirm normal response times

## Strategy Engine Recovery
1. Confirm process/container health
2. Review logs for exceptions or stall behavior
3. Validate upstream feed presence
4. Restart service if needed
5. Confirm strategy metrics are moving again

## Recovery Principles
- Restore service safely
- Validate end-to-end function, not just process uptime
- Capture lessons for future prevention
