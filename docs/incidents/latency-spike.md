# Incident: System Latency Spike

## Summary

A spike in end-to-end latency impacted system responsiveness, increasing processing time across services.

---

## Detection

* Grafana dashboard showed elevated p95/p99 latency
* Alert triggered for API response time threshold

---

## Impact

* Slower processing of market data
* Delayed system responses
* Increased risk of degraded system performance

---

## Investigation

* Analyzed latency metrics across services
* Checked service resource usage (`top`, `htop`)
* Investigated network performance (`ss`, `ping`, `traceroute`)
* Identified bottleneck in downstream service

---

## Root Cause

Resource contention and increased load caused degraded performance in a critical service component.

---

## Resolution

* Restarted affected service
* Rebalanced load across components
* Verified latency improvement in dashboards

---

## Outcome

* Latency returned to acceptable levels
* System responsiveness restored

---

## Preventative Actions

* Added latency-based alerting thresholds
* Improved capacity planning
* Introduced monitoring for resource saturation
