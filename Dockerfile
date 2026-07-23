# ShubhTithi — production image (uv + Python 3.12 + Swiss Ephemeris).
FROM python:3.12-slim-bookworm

# build-essential is a safety net in case pyswisseph builds from source (a
# prebuilt manylinux wheel is used when available; you can drop this to slim the
# image if the build resolves a wheel for your platform). Then install uv.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Faster, reproducible installs; put the venv on PATH.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# 1) Install dependencies first (cached across code changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Copy the app + bundled data and finish the install.
COPY . .
RUN uv sync --frozen --no-dev

# Railway injects $PORT. Bind :: (IPv6, dual-stack) so BOTH the public proxy and
# Railway private networking (IPv6-only) can reach us; 0.0.0.0 is IPv4-only and
# is unreachable over .railway.internal. Shell form so ${PORT} expands.
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8000}"]
