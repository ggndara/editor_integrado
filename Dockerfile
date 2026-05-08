# syntax=docker/dockerfile:1

FROM python:3.10-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    PYTHON=python3.10 \
    TRANSCRIBER_ROOT=/app/deps/14_LetrasAcordesv4 \
    PDF_SAVE_MODE=runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      ffmpeg \
      git \
      libsndfile1 \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY deps/14_LetrasAcordesv4/pyproject.toml deps/14_LetrasAcordesv4/README.md /app/deps/14_LetrasAcordesv4/
COPY deps/14_LetrasAcordesv4/src /app/deps/14_LetrasAcordesv4/src

RUN python -m pip install --upgrade pip "setuptools<81" wheel \
    && python -m pip install "Cython>=3.0" "numpy>=1.24,<3.0" "scipy>=1.10,<2.0" \
    && python -m pip install --no-build-isolation "madmom==0.16.1" \
    && python -m pip install -e "/app/deps/14_LetrasAcordesv4[lyrics,pdf]"

COPY . /app

RUN test -f /app/deps/14_LetrasAcordesv4/scripts/run_full_pipeline.py \
    && test -f /app/deps/15_EditorChordPro/app.js \
    && mkdir -p /app/runtime/uploads /app/runtime/exports /app/deps/14_LetrasAcordesv4/songs

EXPOSE 8080

CMD ["python", "server.py"]
