# Start the backend API on Windows. Defaults to offline demo mode (no API key).
if (-not $env:LLM_PROVIDER)   { $env:LLM_PROVIDER = "fixture" }
if (-not $env:EMBED_PROVIDER) { $env:EMBED_PROVIDER = "sentence_transformers" }
python -m uvicorn api.main:app --reload --port 8000
