FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY mcp-state/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY mcp-state/app/ /app/app/

EXPOSE 8203
CMD ["python", "-m", "app.server"]
