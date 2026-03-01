# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (layer caching).
# Build with: podman build -v ~/.cache/uv:/root/.cache/uv:z ...
# to reuse the host's uv cache and avoid re-downloading ~3 GB of wheels.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself
COPY mtg_collector/ mtg_collector/
RUN uv sync --frozen --no-dev

# Pre-download RapidOCR models so containers don't fetch on first use
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/* \
    && uv run python -c "from rapidocr import RapidOCR, LangRec; RapidOCR(params={'Rec.lang_type': LangRec.EN, 'Global.log_level': 'critical'})"

# Stage 2: Runtime
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy venv and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/mtg_collector /app/mtg_collector

# Pre-built test fixture for fast --test container setup (no network needed)
COPY tests/fixtures/test-data.sqlite /app/test-data.sqlite

# Sample ingest images for recents page test data (used by mtg sample-ingest)
COPY tests/fixtures/sample-*.jpg tests/fixtures/sample-*.jpeg /app/tests/fixtures/

ENV PATH="/app/.venv/bin:$PATH"
ENV MTGC_HOME=/data

EXPOSE 8081

ENTRYPOINT ["mtg", "crack-pack-server", "--port", "8081", "--https"]
