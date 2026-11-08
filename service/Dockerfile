# Inference service image (Task 3). No model weights inside: the model is downloaded from
# object storage (MODEL_URI) at start-up. CPU-only PyTorch keeps the image well under 2 GB.
# Build from the repository root:  docker build -f service/Dockerfile -t ccmini/parser:1.0 .
FROM python:3.12.8-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    TORCH_NUM_THREADS=1 \
    MODEL_CACHE_DIR=/models

WORKDIR /app
COPY service/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY service/app.py service/model.py service/prompting.py /app/
COPY data/schema.json /app/schema.json
RUN useradd --uid 1000 --create-home app && mkdir -p /models && chown app:app /models

USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "25"]
