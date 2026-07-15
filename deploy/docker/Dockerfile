"""Multi-stage Docker build for the Kitty LLM red-teaming framework."""

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definitions first for layer caching
COPY pyproject.toml README.md /app/
COPY src/kitty/ /app/src/kitty/

# Install the package and all dependencies
RUN pip install --upgrade pip \
    && pip install -e ".[all]"

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KITTY_DATABASE_URL="sqlite+aiosqlite:////data/kitty.db" \
    KITTY_CACHE_PATH="/cache"

# Create non-root user and required directories
RUN groupadd -r kitty && useradd -r -g kitty -d /app -s /bin/false kitty \
    && mkdir -p /data /cache /app \
    && chown kitty:kitty /data /cache /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

USER kitty
WORKDIR /app

# API server port
EXPOSE 15500

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:15500/api/v1/health')" || exit 1

# Default command: start the API server
CMD ["kitty", "server", "--host", "0.0.0.0", "--port", "15500"]
