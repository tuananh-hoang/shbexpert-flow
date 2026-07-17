# Build context is the REPO ROOT (see docker-compose.yml `context: .`) so
# this Dockerfile can copy the shared/ package used by both api and worker.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared/ /app/shared/
COPY worker/app/ /app/app/
COPY worker/config/ /app/config/

CMD ["python", "-m", "app.main"]
