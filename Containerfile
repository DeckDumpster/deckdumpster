# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# Marks every image commit this build produces as ours, including this stage's —
# which is a full 983 MB image that nothing else can name. deploy/setup.sh builds
# `mtgc:latest` and tags `mtgc:<instance>`, so the RUNTIME image is findable by
# tag, but a multi-stage build's builder stage is untagged and is NOT in the
# runtime image's `image history`. deploy/store-isolation-gate.sh needs to find
# both: to notice a build that leaked into Podman's default store, and to remove
# it again afterwards (de-y5g). It must be the first instruction in the stage,
# because a layer commit inherits the labels declared before it and not the ones
# after.
LABEL cards.dumpster.mtgc.build=1

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

# Same marker, same reason, first instruction again — see stage 1.
LABEL cards.dumpster.mtgc.build=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy venv and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/mtg_collector /app/mtg_collector

# Pre-built test fixture for fast --test container setup (no network needed)
COPY tests/fixtures/test-data.sqlite /app/test-data.sqlite

# Demo ingest images for recents page sample data
COPY tests/fixtures/sample-*.jpg /app/tests/fixtures/

ENV PATH="/app/.venv/bin:$PATH"
ENV MTGC_HOME=/data

EXPOSE 8081

ENTRYPOINT ["mtg", "crack-pack-server", "--port", "8081", "--https"]
