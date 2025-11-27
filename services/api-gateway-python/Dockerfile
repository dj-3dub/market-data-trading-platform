FROM python:3.12-slim

WORKDIR /app

COPY app/ ./app
RUN pip install --no-cache-dir fastapi uvicorn httpx prometheus-client

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
