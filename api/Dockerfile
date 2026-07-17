# Build context is the REPO ROOT (see docker-compose.yml `context: .`) so
# this Dockerfile can copy the shared/ package used by both api and worker.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# DejaVu Sans has full Vietnamese Unicode coverage (precomposed chars like
# đ/ư/ơ/ệ are outside Latin-1, so reportlab's built-in core fonts —
# Helvetica/Times/Courier — can't render them at all). Installed as a
# standard Debian package rather than checking a font binary into git —
# scripts/pdf_utils.py registers it from this exact path.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared/ /app/shared/
COPY scripts/ /app/scripts/
COPY api/app/ /app/app/
COPY api/alembic/ /app/alembic/
COPY api/alembic.ini /app/alembic.ini

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
