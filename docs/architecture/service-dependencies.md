# Service Dependencies

This document outlines how services depend on each other within the platform and how failures propagate across the system.

Understanding these relationships is critical for effective troubleshooting and incident response.

## Dependency Graph


Market Data Service
↓
Kafka
↓
Strategy Engine
↓
API Gateway
↓
Clients


Monitoring layer:


All Services → Prometheus → Grafana


---

## Service-by-Service Dependencies

### Market Data Service
- Depends on:
  - Kafka (to publish messages)
- Failure impact:
  - No new data enters the system
  - Downstream services may continue running but process stale data

---

### Kafka Broker
- Central dependency for:
  - Market Data Service (producer)
  - Strategy Engine (consumer)
- Failure impact:
  - Complete disruption of event flow
  - System appears "up" but data stops moving

---

### Strategy Engine
- Depends on:
  - Kafka (input stream)
- Provides:
  - Processed outputs and metrics
- Failure impact:
  - No new strategy decisions
  - API may serve stale or incomplete data

---

### API Gateway
- Depends on:
  - Strategy Engine
  - Possibly cached or aggregated data
- Failure impact:
  - External visibility into system is degraded
  - May mask deeper system issues

---

### Prometheus
- Depends on:
  - Service metric endpoints
- Failure impact:
  - Loss of observability
  - Increased mean time to detect issues

---

### Grafana
- Depends on:
  - Prometheus
- Failure impact:
  - Visualization loss only (data may still exist)

---

## Failure Propagation Examples

### Kafka Failure
- Market data cannot be published
- Strategy engine receives no updates
- API serves stale data
- Metrics may appear flat

---

### Strategy Engine Failure
- Market data still flows
- Processing stops
- API becomes stale or inconsistent

---

### API Gateway Failure
- Internal system continues functioning
- External access is disrupted

---

## Key Takeaways

- Not all failures are immediately visible
- “Service up” does not mean “system healthy”
- Observability is required to detect partial failures
- Understanding dependencies reduces recovery time

---

## Future Enhancements

- Visual dependency diagrams
- Automated dependency health checks
- Service-level health scoring
