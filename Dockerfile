# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Tectonic installieren (single static binary)
RUN curl -fsSL https://tectonic-typesetting.github.io/install.sh | sh \
    && mv /root/.tectonic/tectonic /usr/local/bin/tectonic \
    && chmod +x /usr/local/bin/tectonic

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Tectonic Binary aus Builder kopieren
COPY --from=builder /usr/local/bin/tectonic /usr/local/bin/tectonic

# Python-Packages aus Builder kopieren
COPY --from=builder /install /usr/local

# System-Dependencies für LaTeX-Fonts (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfontconfig1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY src/ ./src/
COPY data/ ./data/
COPY .env.example .env.example

RUN mkdir -p /app/output /app/db

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Non-root User für Sicherheit
RUN useradd -r -s /bin/false agent \
    && chown -R agent:agent /app
USER agent

CMD ["python", "-m", "src.main"]
