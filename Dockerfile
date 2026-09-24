# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy project metadata and source code for building dependencies and package
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --prefix=/install ".[bigquery,v4-agent]"

# Final runtime stage
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:/app/src"

# Install curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

# Copy installed python packages from builder
COPY --from=builder /install /install

# Copy application source code and assets
COPY src ./src
COPY assets ./assets
COPY pyproject.toml README.md ./

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "src/ai_search_journey/app.py", "--server.address=0.0.0.0", "--server.port=8080", "--server.headless=true"]
