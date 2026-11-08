# MDP Alloy + Tempo tracing overlay

Copy the files into the root of your existing market-data-trading-platform repository. This is an additive Compose overlay; it does not replace your existing compose file.

## Apply

From repository root, after copying the files:

```bash
# Check any existing Grafana datasource YAML so UID/name 'tempo' is not duplicated.
find monitoring/grafana/provisioning/datasources -maxdepth 1 -type f -print

# Validate effective YAML/Compose service definitions.
docker compose -f docker-compose.yml -f docker-compose.observability.yml config --quiet

# Validate Alloy configuration; pulls the pinned image if necessary.
docker run --rm -v "$PWD/monitoring/alloy/config.alloy:/etc/alloy/config.alloy:ro" grafana/alloy:v1.21.3 validate /etc/alloy/config.alloy

# Start new components only.
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d tempo alloy

# Grafana reads provisioned datasource config when restarted.
docker compose restart grafana

# Check health/logs.
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps tempo alloy
docker compose -f docker-compose.yml -f docker-compose.observability.yml logs --tail=80 tempo alloy
```

Alloy UI: http://127.0.0.1:12345
OTLP gRPC on host: 127.0.0.1:4317; OTLP HTTP on host: 127.0.0.1:4318.
Within Compose network, app services use `http://alloy:4318` for OTLP/HTTP.
Grafana Tempo datasource: http://tempo:3200 (container-to-container only).

## Smoke test

No traces appear until an instrumented app or OTLP-compatible generator sends them. For a real application integration, add SDKs, instrumentation, trace-context propagation through Kafka, and sampling. Export OTLP/HTTP traces to `http://alloy:4318/v1/traces`. Do not set OTEL_TRACES_EXPORTER=otlp without installing an SDK/exporter.

## Notes

- Tempo storage is local and 72-hour retention; use object storage and non-root permissions for production.
- Tempo and Alloy are kept private on the Compose network except Alloy's localhost-only ports.
- Existing Prometheus scrapes and alerts remain untouched.
- Avoid `docker compose down -v`: it deletes named volumes, including Kafka and observability history.
- To manage the full stack with the overlay, always use both `-f` flags (or set `COMPOSE_FILE`).
