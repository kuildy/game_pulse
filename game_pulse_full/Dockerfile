FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN mkdir -p /app/data

EXPOSE 5050

CMD ["gunicorn", "--workers", "1", "--threads", "2", "--timeout", "180", "--bind", "0.0.0.0:5050", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
