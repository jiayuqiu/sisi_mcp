FROM python:3.11-slim

WORKDIR /app

ARG PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn

ENV PIP_INDEX_URL=${PIP_MIRROR}/simple \
    UV_DEFAULT_INDEX=${PIP_MIRROR}/simple \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=8

RUN pip install uv

ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} sisillm && useradd -m -u ${APP_UID} -g ${APP_GID} sisillm || true
RUN mkdir -p /home/sisillm && chown sisillm:sisillm /home/sisillm

COPY pyproject.toml uv.lock ./
COPY mcp_conductor/__init__.py mcp_conductor/__init__.py

# uv.lock is resolved against the Tsinghua mirror, so `uv sync --frozen`
# downloads wheels straight from it; no URL rewriting is needed.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . .

# .python-version pins 3.12 for local development, but the venv in this image is
# built on python:3.11-slim. Remove it so `uv run` reuses the baked venv instead
# of downloading a second interpreter at container start.
RUN rm -f .python-version

RUN mkdir -p ./tmp/images

RUN chown -R sisillm:sisillm /app
RUN mkdir -p /app/.cache/uv && chown -R sisillm:sisillm /app/.cache
RUN mkdir -p /app/.cache/matplotlib && chown -R sisillm:sisillm /app/.cache/matplotlib
USER sisillm
