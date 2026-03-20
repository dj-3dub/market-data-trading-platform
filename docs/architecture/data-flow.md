# Data Flow

This document describes how data moves through the system from ingestion to consumption.

Understanding the data path is essential for diagnosing latency, bottlenecks, and failures.

---

## End-to-End Flow


[ Market Data Service ]
↓
(Kafka Topic)
↓
[ Strategy Engine Consumer ]
↓
(Processed Output)
↓
[ API Gateway ]
↓
(Clients)

Monitoring Path:
All Services → Prometheus → Grafana


---

## Step-by-Step Flow

### 1. Data Generation
- The market data service generates simulated price data
- Data is structured and published to Kafka topics

---

### 2. Event Streaming (Kafka)
- Kafka receives messages from the producer
- Messages are stored temporarily in partitions
- Consumers pull messages at their own pace

---

### 3. Data Consumption
- Strategy engine subscribes to Kafka topics
- Processes incoming data in near real-time
- Generates derived metrics or signals

---

### 4. API Exposure
- API gateway queries internal state or processed outputs
- Provides endpoints for external access
- May introduce latency if dependencies are slow

---

### 5. Observability Pipeline
- Prometheus scrapes metrics from:
  - strategy engine
  - API gateway
  - other services
- Grafana visualizes:
  - latency
  - throughput
  - system health
  - anomalies

---

## Data Flow Characteristics

### Asynchronous Processing
Kafka decouples producers and consumers, allowing independent scaling and resilience.

### Event-Driven Architecture
Services react to incoming data rather than polling synchronously.

### Backpressure Possibility
If consumers lag:
- Kafka retains messages
- Consumer lag increases
- System latency grows

---

## Failure Scenarios in Data Flow

### Producer Failure
- No new data enters system
- Downstream services become stale

### Kafka Failure
- Complete disruption of flow
- All dependent services affected

### Consumer Lag
- Data backlog builds
- Increased latency
- Delayed decision-making

### API Bottleneck
- Data processed but not served efficiently
- Perceived system slowness

---

## Key Metrics to Monitor

- message throughput
- consumer lag
- processing latency
- API response time
- error rate
- data freshness

---

## Future Enhancements

- Add latency tracing between services
- Introduce synthetic transactions
- Track end-to-end processing time
- Add distributed tracing (OpenTelemetry)
