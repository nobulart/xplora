FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    XPLORA_CACHE_DIR=/app/.cache/xplora \
    XPLORA_LOG_LEVEL=WARNING

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p public tweets_media
RUN python -c "import main; main.pre_process_tweets_sync()"

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log --log-level warning"]
