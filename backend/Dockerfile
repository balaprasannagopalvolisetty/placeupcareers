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

# ScrapeGraphAI needs a browser runtime for dynamic career pages, Google Jobs,
# and LinkedIn guest pages in the 6-hour Cloud Run job.
RUN python -m playwright install --with-deps chromium

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p data

# Expose Cloud Run's default port
EXPOSE 8080

# Run with uvicorn. Cloud Run injects PORT=8080.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-2}"]
