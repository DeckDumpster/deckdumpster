# Thin runtime image for CI — no code, no venv, no data baked in.
# Host paths (macOS /opt ↔ VM /var/opt via virtiofs):
#
#   /opt/dd-ci-code/   ← git clone + Linux .venv (built inside container)
#   /opt/dd-ci-data/   ← MTGC_HOME: DB, AllPrintings.json, prices, certs
#
# One-time setup:
#   git clone https://github.com/DeckDumpster/deckdumpster.git /opt/dd-ci-code
#   podman run --rm -v /var/opt/dd-ci-code:/app --entrypoint bash \
#       dd-ci-server -c "cd /app && uv sync --group dev && uv run shot-scraper install"
#   podman run --rm -v /var/opt/dd-ci-code:/app -v /var/opt/dd-ci-data:/data \
#       -e MTGC_HOME=/data --entrypoint /app/.venv/bin/python3 \
#       dd-ci-server /app/.venv/bin/mtg setup --demo
#
# Cron (in deploy repo crontab):
#   # Update CI code, deps, and Chromium daily at 5 AM
#   0 5 * * * podman run --rm -v /var/opt/dd-ci-code:/app --entrypoint bash \
#       dd-ci-server -c "cd /app && git pull && uv sync --group dev && uv run shot-scraper install"
#
# Run (~6s to first response):
#   podman run --rm -d \
#       -v /var/opt/dd-ci-code:/app:O \
#       -v /var/opt/dd-ci-data:/data:O \
#       -e ANTHROPIC_API_KEY \
#       -p 8082:8081 \
#       dd-ci-server

FROM docker.io/library/python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssl libgl1 libglib2.0-0 \
        git gettext-base \
        # Chromium system deps for Playwright/shot-scraper
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libdbus-1-3 libxkbcommon0 libatspi2.0-0 libx11-6 \
        libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
        libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# gh CLI
RUN apt-get update && apt-get install -y --no-install-recommends curl gpg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get purge -y curl gpg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Node.js (needed by Claude CLI)
COPY --from=docker.io/library/node:22-slim /usr/local/bin/node /usr/local/bin/node

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV MTGC_HOME=/data
ENV EASYOCR_MODEL_STORAGE=/app/models/ocr
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright

# Non-root user for Claude CLI (refuses --dangerously-skip-permissions as root).
# Caller uses --userns=keep-id:uid=1000,gid=1000 to map host user → ci.
RUN useradd -m -s /bin/bash -u 1000 ci
ENV HOME=/home/ci

WORKDIR /app
EXPOSE 8081

# No default ENTRYPOINT — caller decides:
#   entrypoint.sh for CI, explicit mtg command for server validation
