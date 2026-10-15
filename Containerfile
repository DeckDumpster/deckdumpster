# The project image: the dependency base (Containerfile.deps, built or pulled by
# deploy/deps-image.sh and passed in as DEPS_IMAGE) plus the project itself.
# There is no default: a build that does not say which base it wants is a bug.
ARG DEPS_IMAGE

FROM ${DEPS_IMAGE}

# Same marker as the base, first instruction again — see Containerfile.deps.
LABEL cards.dumpster.mtgc.build=1

WORKDIR /app

# Install the project itself (dependencies are already in the base's venv)
COPY pyproject.toml uv.lock ./
COPY mtg_collector/ mtg_collector/
RUN uv sync --frozen --no-dev

# Pre-built test fixture for fast --test container setup (no network needed)
COPY tests/fixtures/test-data.sqlite /app/test-data.sqlite

# Demo ingest images for recents page sample data
COPY tests/fixtures/sample-*.jpg /app/tests/fixtures/

ENV PATH="/app/.venv/bin:$PATH"
ENV MTGC_HOME=/data

# The commit this image was built from, served on /health so cdn-check can tell
# the CDN is serving THIS deploy. Last, so a new commit busts no earlier layer.
ARG BUILD_ID
ENV MTGC_BUILD_ID=${BUILD_ID}

EXPOSE 8081

ENTRYPOINT ["mtg", "crack-pack-server", "--port", "8081", "--https"]
