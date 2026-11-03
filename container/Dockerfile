# syntax=docker/dockerfile:1
FROM ollama/ollama:0.40.14 AS ollama
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    HF_HOME=/data/models/huggingface TORCH_HOME=/data/models/torch \
    OLLAMA_MODELS=/data/models/ollama OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_NO_CLOUD=1 OLLAMA_KEEP_ALIVE=30s OLLAMA_MAX_LOADED_MODELS=1 \
    HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0 DO_NOT_TRACK=1 \
    WINWHISPER_DATA=/data HOME=/data/home PYTHONDONTWRITEBYTECODE=1 PATH=/opt/venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv ffmpeg ca-certificates libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ollama /usr/bin/ollama /usr/bin/ollama
COPY --from=ollama /usr/lib/ollama /usr/lib/ollama
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY constraints-linux-py312.txt /app/constraints-linux-py312.txt
# Session-specific CA trust may be provided as a BuildKit secret; never stored.
RUN --mount=type=secret,id=proxy_ca \
    python3 -m venv /opt/venv && \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    /opt/venv/bin/pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu128 -c /app/constraints-linux-py312.txt -r /app/requirements.txt && \
    /opt/venv/bin/pip check && /opt/venv/bin/pip freeze > /app/requirements.resolved.txt
COPY . /app/
RUN chmod +x /app/whisperx-cli
LABEL io.winwhisper.engine="1.0.0"
ENTRYPOINT ["python3", "/app/container_entry.py"]
