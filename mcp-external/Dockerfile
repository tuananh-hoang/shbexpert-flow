FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY mcp-external/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY mcp-external/app/ /app/app/

EXPOSE 8202
CMD ["python", "-m", "app.server"]
