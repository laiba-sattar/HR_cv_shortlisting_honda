# CV Ranking Model — HR CV Shortlisting System

The model layer for the Honda Atlas Cars Pakistan CV shortlisting project.
Takes a job description and a batch of CVs, and returns a ranked shortlist
with a written justification for every score.

## The design in one paragraph

The intelligence comes from **pre-trained models**, not from training on
Honda's data. An LLM reads each CV in whatever format and wording it happens
to use and returns structured JSON. An embedding model compares skills and
experience **by meaning**, so "ReactJS" matches "React" and "client relations"
matches "customer support" without any keyword list. Where a candidate's tool
differs but the underlying competence transfers, a second LLM call decides how
much credit to give **and writes down why**. Only the final arithmetic — the
33/33/33 weighting — is deterministic, because a score that changes between
runs would make the audit trail worthless.

There is no hand-maintained synonym table anywhere in this code. That is
deliberate: skill lists go stale, and someone always writes a skill a way
nobody anticipated.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in LLM_API_KEY
```

### Step 1 — verify the embedding model actually understands skills

**Do this before anything else.** It is the single most important check in
the project: it tests whether the model recognises the same skill written
differently, related-but-different tools, and genuinely unrelated ones.

```bash
python check_semantics.py
```

You get a PASS/FAIL table. If "same" cases fail, either the model is too weak
or `SKILL_MATCH_THRESHOLD` is wrong — change one, re-run, compare. Tune
against this table rather than by guesswork, and re-run it whenever you change
`EMBED_MODEL`.

### Step 2 — run a ranking

```bash
python rank_cvs.py --jd data/jds/mech_design_engineer.txt \
                   --cvs data/sample_cvs --top 5
```

### Step 3 — try it without an API key

Fixture mode replays recorded extraction output so the whole pipeline runs
offline. Useful for testing scoring changes and for CI.

```bash
python make_fixtures.py
LLM_PROVIDER=fixture EMBED_PROVIDER=hash python rank_cvs.py \
    --jd data/jds/mech_design_engineer.txt --cvs data/sample_cvs --top 5
```

`EMBED_PROVIDER=hash` has **no semantic understanding** — it exists to prove
the wiring, not to produce meaningful rankings. The code warns you when it is
active. Never use it for a real ranking.

---

## The mandatory JD rule, enforced here

If the job description does not mention **age**, **experience** or
**qualification**, and no manual value was supplied, `run_ranking()` raises
`MissingRequirementsError` and nothing is scored.

This duplicates the frontend check on purpose. The frontend check is a
convenience; this one is the guarantee, because the API can be called directly.

A manually supplied value **always overrides** the job description:

```bash
python rank_cvs.py --jd data/jds/production_engineer_no_age.txt \
                   --cvs data/sample_cvs --top 5 \
                   --experience "0-2 years" --experience-min 0 \
                   --age "20-30 years" --age-min 20 --age-max 30
```

---

## How the three scores work

**Qualification (33%)** — academic level is compared ordinally (bachelor's <
master's < PhD: a numeric fact, no model needed). Field of study is compared
**semantically**, and applied as a *multiplier* on the level score. A BBA in
Finance against a mechanical engineering role scores near zero rather than
inheriting ~60% just for being a bachelor's degree.

**Relevant experience (33%)** — not total years. Each role's duration is
weighted by how semantically close it is to the JD:

```
relevant_years = Σ (years_in_role × relevance × employment_type_weight)
```

Roles below `EXPERIENCE_RELEVANCE_FLOOR` contribute **zero**. Without that
floor, a long career in an unrelated field slowly accumulates "relevant" years
through many small similarity values — seven years of accountancy scoring
against an engineering vacancy. Internships and part-time roles are weighted
by `INTERNSHIP_WEIGHT` / `PART_TIME_WEIGHT`, which are **HR policy decisions**,
not modelling ones — confirm them with the HR stakeholder.

**JD & skills (33%)** — each required skill is resolved in three tiers:

| Similarity | Tier | Cost | Credit |
|---|---|---|---|
| ≥ `SKILL_MATCH_THRESHOLD` | direct match | free | 1.0 |
| middle band | LLM transferability check | 1 call | 0.0–1.0, with written reasoning |
| < `SKILL_CONSIDER_THRESHOLD` | unrelated | free | 0.0 |

The middle tier is what handles "different tech stack, but it transfers".
Its output includes a sentence a recruiter can read and challenge, e.g.
*"Candidate used Vue, not React. Both are component-based frontend frameworks
with similar state-management patterns — transferable with short ramp-up."*

**Age is never scored.** It is checked against the requirement and reported
as a flag for the human reviewer, because age-based screening is a policy
decision a person should make explicitly, not something buried in a number.

---

## Proving accuracy before anyone trusts it

```bash
python eval/evaluate.py --gold eval/gold --cvs data/sample_cvs \
                        --jd data/jds/mech_design_engineer.txt
```

Reports **field-level extraction accuracy** (skills F1, degree-level accuracy,
experience-years error) and **ranking agreement with HR** (Spearman's rho,
Kendall's tau, top-N overlap).

To build a real gold set, have HR extract the correct fields for 50–100 CVs
and manually rank them against 2–3 real JDs, then write one JSON file per CV
into `eval/gold/` (format documented at the top of `eval/evaluate.py`).

Use two independent annotators on a subset and check they agree with each
other. If two HR reviewers can't agree on the right answer, no model can be
held to a single "correct" one either — better to know that before building
on it.

Suggested pilot bar: **rho ≥ 0.7** and **top-10 overlap ≥ 0.7**. Agree the
real threshold with HR before the system influences any hiring decision.

---

## Tests

```bash
LLM_PROVIDER=fixture EMBED_PROVIDER=hash python -m pytest tests/ -q
```

24 tests covering the rules that must hold regardless of which model is
configured: the priority rule, the blocking rule, 33/33/33 weighting,
determinism and tie-breaking, score bounds, age handling, and the two scoring
guards described above. Two of these exist because running the sample batch
exposed real flaws — a long unrelated career scoring 100% on experience, and a
wrong-field degree scoring 61%.

---

## Choosing models

**LLM (extraction + transferability).** Any strong instruction-following model
with structured output. Hosted: Claude or GPT-class. Self-hosted: Qwen2.5
14B+ or Llama 3.x 70B via vLLM or Ollama (set `LLM_PROVIDER=ollama`).

**Embeddings.** Two things matter for this use case: **≥ 8K context** so a
full CV and JD fit in one pass, and **genuine multilingual support**, because
Pakistani CVs mix English with Urdu terms and local institution names.
Current candidates worth benchmarking with `check_semantics.py`:

- `jinaai/jina-embeddings-v4` — strong open-source multilingual, 8K context
- `BAAI/bge-m3` — proven multilingual, 8K context
- `Qwen/Qwen3-Embedding-0.6B` — lighter, instruction-aware
- Hosted: Gemini Embedding, Voyage

`all-MiniLM-L6-v2` is the default here because it is small and fast for
development. It is **not** a production choice — its context window is short
and it is English-only.

---

## On fine-tuning

Not yet, and possibly never for extraction. The semantic understanding this
system needs already exists in the pre-trained models; fine-tuning on a few
hundred Honda CVs would not add it, and on a small dataset risks degrading it
(catastrophic forgetting) — costing you exactly the flexible matching you
want.

Fine-tuning earns its place later, once ~500–1,000 real labelled examples
exist, for things the base model genuinely cannot know: Pakistani institution
names, Honda-internal role titles, and calibration to HR's actual shortlisting
judgement. Do it with LoRA on top of a strong base model, and **benchmark it
against the prompted baseline on the same eval set** — if it doesn't win,
don't ship it.

Never fine-tune the 33/33/33 weighting. It is fixed by the product spec.

---

## Wiring into the backend

```python
from cv_ranker import prepare_job, run_ranking, MissingRequirementsError

job = prepare_job(jd_text=jd_text, manual_overrides={
    "age": {"text": "22-30", "min_value": 22, "max_value": 30},
})

missing = job.missing_requirements()   # -> ["age"] etc; block the run if non-empty

try:
    run = run_ranking(job, cv_paths, progress=lambda i, n, p: print(i, n))
except MissingRequirementsError as e:
    return {"error": "missing_requirements", "fields": e.missing}

return run.to_dict(top_n=10)
```

`run.to_dict()` returns exactly what the frontend needs — final score, the
three sub-scores, a written explanation for each, matched and missing skills,
per-skill reasoning, flags, and the model/engine versions that produced the
run. Store the whole object: it is the audit record.

---

## Open decisions still blocking production

1. **Hosting and data residency.** Can CV text go to a third-party API, or
   must everything run on Honda infrastructure? This determines whether you
   use hosted models or self-host open-weight ones, and it is the single
   decision that most affects cost and timeline.
2. **Access to real CVs.** 100–200 anonymised CVs covering the formats Honda
   actually receives, ideally from closed positions where the shortlist and
   hire are known. This has the longest lead time — start the request now.
3. **Internship / part-time weighting.** Currently 0.5 / 0.6. HR's call.
4. **Bias audit before go-live.** Swap tests holding CV content constant while
   varying name, gender-coded cues and university tier. Hiring AI is treated
   as high-risk under the EU AI Act and requires bias audits under NYC Local
   Law 144; Pakistan has no equivalent binding rule yet, but this is the
   standard Honda's global operations are held to, and it is the right thing
   to do regardless.
5. **Shadow-run period.** Run alongside HR's manual process for 4–8 weeks
   without influencing decisions, then compare before switching on.

---

## Layout

```
cv_ranker/
  schema.py       Extraction contract + JobProfile (priority & blocking rules)
  llm.py          Provider abstraction: anthropic / openai / ollama / fixture / stub
  embeddings.py   Embedding backends + cosine similarity
  documents.py    PDF / DOCX / TXT reading, OCR fallback
  extract.py      Layer 1: LLM extraction + deterministic validation pass
  matching.py     Layer 2 & 3: semantic skill matching + transferability
  scoring.py      Deterministic 33/33/33 scoring engine
  pipeline.py     End-to-end orchestration, parallel extraction, per-file isolation
  prompts/        The three prompts — edit these to change model behaviour
check_semantics.py  Model sanity check — run first
rank_cvs.py         CLI
eval/evaluate.py    Accuracy harness
tests/              24 tests of the invariants
```
