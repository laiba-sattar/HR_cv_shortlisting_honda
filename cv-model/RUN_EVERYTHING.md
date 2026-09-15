# Running the whole system

Three pieces. Two terminals.

| Piece | Folder | Port |
|---|---|---|
| Backend API (model) | `cv-model` | 8000 |
| Frontend (website) | `honda-hr-frontend` | 5173 |

---

## Terminal 1 — Backend

```bash
cd cv-model
python -m venv .venv
.venv\Scripts\activate            # Windows;  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Then start it. **No API key needed** for this mode:

```powershell
# Windows PowerShell
$env:LLM_PROVIDER="fixture"
python -m uvicorn api.main:app --reload --port 8000
```

```bash
# macOS / Linux
LLM_PROVIDER=fixture python -m uvicorn api.main:app --reload --port 8000
```

Check it: open <http://localhost:8000/api/health> — you should see JSON.
Interactive API docs: <http://localhost:8000/docs>

`LLM_PROVIDER=fixture` replays recorded extraction for the five sample CVs, so
the pipeline runs end-to-end offline. Embeddings run **locally and for real**
(`sentence-transformers` downloads the model on first use, ~90MB).

## Terminal 2 — Frontend

```bash
cd honda-hr-frontend
npm install
npx vite
```

Open <http://localhost:5173>.

The left panel shows a banner telling you which mode you are in:

- **Live backend** (green/amber) — connected, real pipeline
- **Demo mode** (grey) — backend not reachable, simulated data

---

## Test it end to end

1. Job title: `Mechanical Design Engineer`
2. Paste the contents of `cv-model/data/jds/mech_design_engineer.txt`
3. Press **Read requirements** — all three fields should come back green with
   the exact sentence quoted from the advert, and the skills list auto-fills.
4. Upload the five CVs from `cv-model/data/sample_cvs/`
5. Press **Rank CVs** → real ranking appears. Click a row to expand the breakdown.

**Test the blocking rule:** press Clear, paste
`cv-model/data/jds/production_engineer_no_age.txt` instead — it deliberately
omits age and experience. Press Rank CVs and the backend refuses (HTTP 422),
listing both fields. Fill them in and it proceeds.

---

## Turning on real extraction

Fixture mode only knows the five sample CVs. For real CVs you need a real LLM:

```powershell
$env:LLM_PROVIDER="anthropic"      # or "openai"
$env:LLM_API_KEY="sk-..."
python -m uvicorn api.main:app --reload --port 8000
```

Self-hosted instead (no data leaves your infrastructure):

```powershell
$env:LLM_PROVIDER="ollama"
$env:LLM_MODEL="qwen2.5:14b-instruct"
$env:LLM_BASE_URL="http://localhost:11434/v1"
```

Which of these you use is the hosting decision still waiting on your IT
supervisor.

---

## Before trusting any result

```bash
cd cv-model
python check_semantics.py
```

Tests whether the embedding model recognises "ReactJS" = "React", that Vue is
related to React, and that unrelated things stay unrelated. Run this before
tuning anything else — it is how you choose a model on evidence.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Which providers are active, plus warnings |
| POST | `/api/jd/analyze` | Three-field presence check on a JD |
| POST | `/api/runs` | Start a ranking (returns `run_id`, 202) |
| GET | `/api/runs/{id}` | Progress, then results |
| GET | `/api/runs` | History of saved runs |
| DELETE | `/api/runs/{id}` | Delete a run |
| GET | `/api/audit` | Append-only audit log |

Data is stored in `cv-model/storage/app.db` (SQLite) and uploaded files under
`cv-model/storage/runs/`. Delete that folder to reset.
