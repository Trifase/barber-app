FROM python:3.14-slim

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for high-performance dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency specifications first for Docker layer caching
COPY pyproject.toml uv.lock* ./

# Install all dependencies into system Python
RUN uv pip install --system -r pyproject.toml

# Copy repository code
COPY . /app

# Expose port 7525
EXPOSE 7525

# Start Uvicorn with auto-reload for instant development feedback with mounted volumes
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "7525", "--reload"]
