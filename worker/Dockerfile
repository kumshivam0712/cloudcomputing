# Teacher-labelling worker + cleaner image (Task 1).
# Build from the repository root:  docker build -f worker/Dockerfile -t ccmini/worker:1.0 .
FROM python:3.12.8-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install -r /app/worker/requirements.txt

COPY worker/teacher.py worker/storage.py worker/worker.py worker/clean.py /app/worker/
COPY prompts/teacher_prompt.txt /app/prompts/teacher_prompt.txt
COPY data/schema.json /app/data/schema.json

ENV PROMPT_FILE=/app/prompts/teacher_prompt.txt
USER 1000:1000
ENTRYPOINT ["python", "/app/worker/worker.py"]
