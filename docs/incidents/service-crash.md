# Incident: Strategy Engine Service Crash

## Summary

The strategy engine service became unavailable due to a runtime failure, interrupting data processing and downstream signal generation.

---

## Detection

* Health check endpoint failed
* Alert triggered for service downtime
* API returned incomplete or missing data

---

## Impact

* Interruption in data processing pipeline
* Downstream services received incomplete data
* Temporary loss of system functionality

---

## Investigation

* Verified service status (`ps aux | grep strategy-engine`)
* Reviewed logs via `journalctl` and application logs
* Checked recent deployment or configuration changes

---

## Root Cause

Unhandled exception in processing logic caused the service to terminate.

---

## Resolution

* Restarted service
* Validated successful recovery via health endpoint
* Confirmed data flow resumed

---

## Outcome

* Service restored with minimal downtime
* System returned to normal operation

---

## Preventative Actions

* Added improved exception handling
* Enhanced logging for debugging
* Implemented alerting for early crash detection
