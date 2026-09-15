# Running for real (not demo mode)

Demo/fixture mode only knows the 5 bundled sample CVs. To process **real CVs**
you need a real LLM. Everything else already runs for real:

| Part | Needs an API key? |
|---|---|
| JD requirement check (age / experience / qualification) | **No** — rule-based, works on any JD |
| Semantic skill matching ("ReactJS" = "React") | **No** — embedding model runs locally |
| CV extraction (reading a CV into structured data) | **Yes** |
| Skill transferability reasoning | **Yes** |

---

## Option A — Groq (fastest to get going, free tier)

1. Sign up at <https://console.groq.com> and create a key at
   <https://console.groq.com/keys> (starts with `gsk_`).
2. In `cv-model`, copy `.env.example` to `.env` and set:

   ```
   LLM_PROVIDER=groq
   LLM_MODEL=openai/gpt-oss-120b
   LLM_API_KEY=gsk_your_key_here
   ```

   Check <https://console.groq.com/docs/models> for the current model list —
   names change, and a wrong name gives a "model not found" error.

3. Restart the backend:

   ```powershell
   cd bundle\cv-model
   .venv\Scripts\activate
   python -m uvicorn api.main:app --reload --port 8000
   ```

   Note: with a `.env` file you no longer set `$env:LLM_PROVIDER` by hand.

4. Confirm at <http://localhost:8000/api/health> — `llm_provider` should say
   `groq` and the fixture warning should be gone.

Other hosted providers work identically — set `LLM_PROVIDER` to `grok`,
`openai`, `anthropic`, `deepseek`, `openrouter` or `together` and supply the
matching key. No base URL needed for those.

---

## Option B — Fully local, nothing leaves your machine

Better answer for real Honda candidate data, and free.

1. Install Ollama: <https://ollama.com/download>
2. Pull a model (~5GB, needs about 8GB RAM):

   ```
   ollama pull qwen2.5:7b-instruct
   ```

   With 16GB+ RAM a larger model extracts more accurately — check
   <https://ollama.com/library> for current options.

3. In `.env`:

   ```
   LLM_PROVIDER=ollama
   LLM_MODEL=qwen2.5:7b-instruct
   LLM_BASE_URL=http://localhost:11434/v1
   ```

4. Leave Ollama running, restart the backend.

---

## A note on data residency

Options A sends CV text to a third-party server outside Pakistan. For the
bundled sample CVs or your own test files that is fine. For **real candidate
CVs** it needs sign-off from your IT supervisor — that is the hosting decision
still open on this project. Option B avoids the question entirely: the CV text
never leaves the machine.

---

## Then try it with real CVs

1. Start backend and frontend as usual, open <http://localhost:5173>.
2. Banner should read **Live backend — groq** (or `ollama`).
3. Paste or upload a real job description → **Read requirements**.
4. Upload real CVs (PDF/DOCX/TXT) → **Rank CVs**.
5. Expand a candidate: you now get real extracted education and work history,
   and where a skill differs but transfers, a written explanation of why.

---

## If something goes wrong

| Symptom | Cause |
|---|---|
| `model not found` / `does not exist` | Wrong `LLM_MODEL` — check the provider's model list |
| `401` / `invalid api key` | Key wrong, or `.env` not being read — confirm it sits in `cv-model/` |
| Health still says `fixture` | Backend didn't restart, or `.env` is in the wrong folder |
| `rate limit` | Free tiers are limited; wait, or lower `--workers` |
| CV extraction is poor quality | Model too small — try a larger one and re-check |

Run `python check_semantics.py` any time to confirm the embedding side is
working — it needs no API key.
