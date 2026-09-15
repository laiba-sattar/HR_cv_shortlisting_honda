# Builds one image that serves both the website and the API on one address.
#
# Stage 1 builds the React site. Stage 2 is the Python service, which serves
# that build from ./web alongside its own /api routes.

# ---------------------------------------------------------------------------
# Stage 1 — the website
# ---------------------------------------------------------------------------
# Pulled from Amazon's public mirror of the official images rather than from
# Docker Hub directly. Shared CI builders hit Docker Hub's anonymous pull
# limits and its network from some regions is unreliable — either shows up as
# "failed to resolve source metadata ... i/o timeout", which is a failure of
# the very first build step and looks alarmingly like a broken Dockerfile.
# Same images, different door.
FROM public.ecr.aws/docker/library/node:20-slim AS web

WORKDIR /build
COPY honda-hr-frontend/package*.json ./
# `npm ci` is the strict one: it installs exactly what package-lock.json says
# and refuses if the lock and package.json disagree. That is the right default,
# but a lock file regenerated on a machine where npm is misbehaving can drift
# out of step, and a deploy should not die for that. Fall back to a normal
# install rather than leave the build stuck.
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY honda-hr-frontend/ ./
# No VITE_API_URL: the built site calls the API on its own origin.
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — the service
# ---------------------------------------------------------------------------
FROM public.ecr.aws/docker/library/python:3.11-slim

# poppler-utils and tesseract let scanned, image-only CVs be read at all;
# without them those files fail instead of falling back to OCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs the container as uid 1000, which cannot write to a
# root-owned working directory. Create the user up front and own everything.
RUN useradd -m -u 1000 app
USER app
ENV PATH="/home/app/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /home/app/service

COPY --chown=app:app cv-model/requirements.txt ./
# The CPU-only torch index keeps the image around 1GB instead of 6GB — there is
# no GPU here and the embedding model runs fine on CPU.
RUN pip install --no-cache-dir --user \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

COPY --chown=app:app cv-model/ ./
COPY --chown=app:app --from=web /build/dist ./web

# The embedding model is NOT baked into the image.
#
# It was, and that is the better arrangement — the first visitor does not wait
# a minute for a download, and a restart does not repeat it. But the download
# runs unauthenticated against the Hugging Face hub, which rate-limits it, and
# on this builder that step kept taking the whole build down after ten minutes.
# A build that never finishes is worse than a slow first request.
#
# The API warms the model in a background thread at startup (see the startup
# event in api/main.py), so the wait lands before anyone signs in rather than
# in the middle of a ranking. HF_HOME points the cache at the app user's home
# so it survives for the life of the container.
ARG EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

ENV EMBED_MODEL=${EMBED_MODEL} \
    PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
