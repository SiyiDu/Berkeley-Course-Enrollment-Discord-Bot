FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY engine/requirements.txt engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

COPY engine /app/engine
COPY memory /app/memory
COPY web /app/web
COPY shared /app/shared

EXPOSE 8000

CMD ["python", "-m", "engine.berkeley_engine.api"]
