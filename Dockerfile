# --- Stage 1: Build stage ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
# Use copy mode instead of symlinks (better for Docker layers)
ENV UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies to system Python (survives volume mount)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --format requirements-txt --no-hashes -o requirements.txt && \
    uv pip install --system -r requirements.txt

# --- Stage 2: Runtime stage ---
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy installed packages from builder (to system site-packages)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app source (will be overwritten by volume mount in compose)
COPY src/ ./src/
COPY main.py .
COPY pyproject.toml .

ENV PYTHONPATH=/app

CMD ["python", "main.py"]