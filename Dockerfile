# MotionProof: the API, the simulations and the built web app in one image.
#
# On your own computer (no sign-in, reachable from this computer only):
#   docker run --rm -p 127.0.0.1:8000:8000 -e MOTIONPROOF_LOCAL=1 -v motionproof-data:/data IMAGE
# Without MOTIONPROOF_LOCAL=1 the server asks for an account.

FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
# shared libraries the CAD kernel and VTK load, which the slim image leaves out
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libx11-6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY motionproof/ motionproof/
RUN uv sync --locked --no-dev
COPY --from=web /web/dist frontend/dist

RUN useradd --create-home motionproof && mkdir /data && chown motionproof /data
USER motionproof
ENV PATH=/app/.venv/bin:$PATH
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=30s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)"
CMD ["motionproof", "serve", "--host", "0.0.0.0", "--home", "/data"]
