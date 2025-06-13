FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
   PYTHONUNBUFFERED=1 \
   PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
   gcc \
   curl \
   && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY requirements.txt .
COPY .env* ./

RUN pip install --no-cache-dir --upgrade pip \
   && pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/logs && chown -R appuser:appuser /app/logs

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]