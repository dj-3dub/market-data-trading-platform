FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir prometheus-client==0.21.1
COPY probe.py .
USER 65534
CMD ["python", "probe.py"]
