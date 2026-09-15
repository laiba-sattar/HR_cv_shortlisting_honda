#!/usr/bin/env bash
# Start the backend API. Defaults to offline demo mode so it runs with no API key.
export LLM_PROVIDER="${LLM_PROVIDER:-fixture}"
export EMBED_PROVIDER="${EMBED_PROVIDER:-sentence_transformers}"
python -m uvicorn api.main:app --reload --port 8000
