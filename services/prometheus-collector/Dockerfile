FROM prom/prometheus:v3.1.0 AS prometheus
FROM python:3.12-slim
COPY --from=prometheus /bin/prometheus /bin/prometheus
COPY --from=prometheus /bin/promtool /bin/promtool
COPY collector.py /app/collector.py
USER 65534
ENTRYPOINT ["python", "/app/collector.py"]
