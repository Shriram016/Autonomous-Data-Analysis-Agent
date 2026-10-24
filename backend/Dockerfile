# The ADAA backend image: one image for the worker now, and for the API in M1.5.
# Build context is the repo root, because the code also needs semantic_layer/, prompts/
# and config/. Secrets are never copied in: .env is read at run time (see .dockerignore).
#
#   docker compose -f infra/docker-compose.yml --env-file .env build worker

FROM python:3.12-slim

# uv, the same version as on the builder's machine, so it reads uv.lock the same way.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

# Keep the repo layout: settings.py finds the repo root three folders above itself.
WORKDIR /app/backend
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/backend/.venv/bin:$PATH"

# 1) Dependencies only, from the lock file: exact versions and hashes. This layer is
#    cached, so a code change does not reinstall every package.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) The code and the files it reads at run time.
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY semantic_layer /app/semantic_layer
COPY prompts /app/prompts
COPY config /app/config
RUN uv sync --frozen --no-dev

# Run as a normal user, not root: a bug in the app can't change the image.
RUN useradd --create-home adaa && chown -R adaa /app
USER adaa

# The default job of this image: a Celery worker. The API (M1.5) will override this.
CMD ["celery", "-A", "adaa.worker.tasks", "worker", "--loglevel=INFO", "--concurrency=2"]
