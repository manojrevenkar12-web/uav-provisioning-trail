# The station software, the traceability server and the console in one image, with the emulated line's tools
# (QEMU and the ARM toolchain) so `uavsim run` works inside it. It needs PostgreSQL (UAV_DATABASE_URL).
FROM node:22-slim AS console
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
RUN apt-get update -q && apt-get install -y -q --no-install-recommends qemu-system-arm gcc-arm-none-eabi make \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UAV_ROOT=/app UAV_DATA=/app/data UAV_WEB=/app/web/dist
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
COPY releases ./releases
COPY firmware ./firmware
COPY campaigns ./campaigns
COPY heldout ./heldout
COPY --from=console /web/dist ./web/dist
RUN useradd --uid 10001 --no-create-home uav && mkdir -p /app/data /app/firmware/build && chown -R uav /app/data /app/firmware
USER uav
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uavtrail", "serve", "--host", "0.0.0.0", "--port", "8000"]
