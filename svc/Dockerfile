FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if required by scipy/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy uv.lock, pyproject.toml, and README.md to install dependencies cleanly
COPY pyproject.toml uv.lock README.md ./
# Install uv and dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the FastAPI application using the virtual environment created by uv
CMD ["/app/.venv/bin/python", "main.py"]
