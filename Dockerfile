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

ARG TRANSCRIBER_REPO=https://github.com/ggndara/audio_a_acordes.git
ARG TRANSCRIBER_REF=afcef91d083e07d2cf8627db576c6283a0bfb0ce
ARG EDITOR_REPO=https://github.com/ggndara/15_EditorChordPro.git
ARG EDITOR_REF=abf8db896dbada853358b40a20a6486869340413

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      ffmpeg \
      git \
      libsndfile1 \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none --no-checkout "$TRANSCRIBER_REPO" /app/deps/14_LetrasAcordesv4 \
    && git -C /app/deps/14_LetrasAcordesv4 checkout "$TRANSCRIBER_REF" \
    && git clone --filter=blob:none --no-checkout "$EDITOR_REPO" /app/deps/15_EditorChordPro \
    && git -C /app/deps/15_EditorChordPro checkout "$EDITOR_REF"

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
