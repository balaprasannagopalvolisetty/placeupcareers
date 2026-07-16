FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    TRANSFORMERS_CACHE=/models \
    PORT=8080

WORKDIR /srv/ats-model
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py .

RUN useradd --create-home --uid 10001 model && mkdir -p /models && chown -R model:model /srv/ats-model /models
USER model

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

