FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY tools-mock/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY tools-mock/app/ /app/app/

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
