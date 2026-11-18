# Stage 1: build the SvelteKit frontend to static files.
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the API, which also serves the built frontend and the artwork.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
COPY --from=infisical/cli:0.45.11 /bin/infisical /usr/local/bin/infisical

# uid 1000 matches jb on the host, so files in the bind-mounted data/ keep their owner.
RUN useradd --uid 1000 --create-home --home-dir /home/app app
ENV HOME=/home/app \
    PATH=/app/.venv/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY api/ api/
COPY ingest/ ingest/
COPY --from=web /web/build web/build
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh

# data/ (pokedex.db, app.db, images/) is not in the image. Mount it at /app/data.
USER app
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
