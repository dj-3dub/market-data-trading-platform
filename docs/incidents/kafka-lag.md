# Incident: Kafka Consumer Lag Spike

## Summary

A spike in Kafka consumer lag caused delayed processing of market data events, increasing end-to-end latency and risking stale data exposure.

---

## Detection

* Grafana alert triggered: `consumer_lag > threshold`
* Observed increasing backlog in Kafka metrics dashboard

---

## Impact

* Delayed processing of incoming market data
* Increased latency in downstream services
* Potential for stale data affecting system behavior

---

## Investigation

* Checked consumer group offsets using Kafka tooling
* Reviewed service logs for processing delays
* Verified CPU and memory utilization (`top`, `htop`)
* Confirmed no broker-side issues

---

## Root Cause

Consumer service was under-provisioned relative to incoming message rate, causing backlog accumulation.

---

## Resolution

* Restarted affected consumer service
* Scaled additional consumer instances
* Monitored lag reduction in Grafana

---

## Outcome

* Consumer lag returned to normal levels
* Message processing stabilized
* Latency normalized

---

## Preventative Actions

* Added alerting threshold for early lag detection
* Implemented auto-scaling strategy for consumers
* Improved visibility into processing throughput
