FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY mcp-deterministic/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY mcp-deterministic/app/ /app/app/

EXPOSE 8200
CMD ["python", "-m", "app.server"]
