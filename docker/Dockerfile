# Spare Parts Request System (SPRS) container image.
#
# Build from the PROJECT ROOT (the build context must contain src/ and requirements.txt):
#   docker build -f docker/Dockerfile -t spare-parts-app:v1 .
#
# Two stages:
#   builder - creates a virtual environment and installs dependencies
#   runtime - copies only that virtual environment and the application code,
#             and runs as an unprivileged user
#
# The app is served by Gunicorn with ONE worker process and several threads.
# JsonStore protects data.json with a threading.Lock, which only works inside
# a single process. Do not raise --workers above 1 while storage is a JSON file.

ARG PYTHON_IMAGE=python:3.10-slim

# ---------------------------------------------------------------- builder ----
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install "gunicorn>=22,<24"

# ---------------------------------------------------------------- runtime ----
FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="spare-parts-app" \
      org.opencontainers.image.description="Spare Parts Request System - Flask app with JSON file storage"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    SPRS_HOST=0.0.0.0 \
    SPRS_PORT=5000 \
    SPRS_DATA_FILE=/data/data.json

# Unprivileged user. /data is the only writable application path.
RUN groupadd --system --gid 10001 sprs \
 && useradd --system --uid 10001 --gid sprs --no-create-home --shell /usr/sbin/nologin sprs \
 && mkdir -p /data \
 && chown sprs:sprs /data \
 && chmod 0750 /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Code stays owned by root, so the running app cannot modify itself.
COPY src/ /app/src/

USER sprs

# data.json lives here. Mount a named volume or a directory, never a single file:
# atomic writes create a temporary file next to data.json and rename it over the original.
VOLUME ["/data"]

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import json,sys,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4); sys.exit(0 if json.load(r).get('status') == 'ok' else 1)"]

CMD ["gunicorn", \
     "--chdir", "/app/src", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "8", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
