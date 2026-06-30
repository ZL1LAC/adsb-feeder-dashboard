FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY scripts/install-muninn.sh scripts/feeder-env.sh scripts/readsb-upload.sh scripts/
COPY muninn/ muninn/
RUN bash scripts/install-muninn.sh

COPY dashboard/ dashboard/
COPY pi-agent/ pi-agent/
COPY feeder.env.example feeder.env.example
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh dashboard/*.sh scripts/*.sh 2>/dev/null || true

ENV FEEDER_REPO_ROOT=/app \
    FEEDER_MUNINN_ROOT=/app/muninn \
    FEEDER_DEPLOY_MODE=split \
    FEEDER_DATA_DIR=/data \
    FEEDER_API_HOST=0.0.0.0 \
    FEEDER_API_PORT=8765 \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8765

ENTRYPOINT ["/entrypoint.sh"]
