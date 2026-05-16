FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PDF parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker cache optimization
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p data

# Expose Cloud Run's default port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, httpx; httpx.get(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/api/health')" || exit 1

# Run with uvicorn. Cloud Run injects PORT=8080; local Docker falls back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
