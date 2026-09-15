"""
Central configuration.

Everything that could differ between "pilot on a laptop" and "production on
Honda infrastructure" is a setting here, so that decision does not require
code changes. Values come from environment variables (a .env file is read
if python-dotenv is installed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional convenience
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    # --- LLM (extraction + transferability reasoning) ----------------------
    # provider: "anthropic" | "openai" | "ollama" | "stub"
    #   ollama -> any self-hosted OpenAI-compatible endpoint (vLLM, Ollama, TGI)
    #   stub   -> no network; returns fixtures. For tests and offline dev only.
    llm_provider: str = _env("LLM_PROVIDER", "stub")
    llm_model: str = _env("LLM_MODEL", "claude-sonnet-4-6")
    llm_base_url: str = _env("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_api_key: str = _env("LLM_API_KEY", "")
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0"))
    llm_max_tokens: int = int(_env("LLM_MAX_TOKENS", "4096"))
    llm_timeout: float = float(_env("LLM_TIMEOUT", "120"))
    # Longest a rate limit is worth waiting out. A per-minute limit clears well
    # inside this; a daily quota does not, and is reported as exhausted rather
    # than silently holding a ranking open for half an hour.
    llm_rate_limit_max_wait: float = float(_env("LLM_RATE_LIMIT_MAX_WAIT", "120"))

    # --- Embeddings (semantic matching) -----------------------------------
    # provider: "sentence_transformers" | "openai" | "hash"
    #   hash -> deterministic offline stand-in. Structure only, NOT real
    #           semantics. Never use for real ranking.
    embed_provider: str = _env("EMBED_PROVIDER", "sentence_transformers")
    # Production candidates, in rough order of preference:
    #   jinaai/jina-embeddings-v4        strong multilingual, 8K context
    #   Qwen/Qwen3-Embedding-0.6B        light, instruction-aware
    #   BAAI/bge-m3                      proven multilingual, 8K context
    # all-MiniLM-L6-v2 is a fast default for development only.
    embed_model: str = _env("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    embed_batch_size: int = int(_env("EMBED_BATCH_SIZE", "32"))

    # --- Matching thresholds ----------------------------------------------
    # Cosine similarity at or above this counts as the same skill, no LLM call.
    skill_match_threshold: float = float(_env("SKILL_MATCH_THRESHOLD", "0.72"))
    # Below this, don't even ask the LLM about transferability — it's unrelated.
    skill_consider_threshold: float = float(_env("SKILL_CONSIDER_THRESHOLD", "0.30"))
    # Cap on transferability LLM calls per candidate (cost control).
    max_transferability_calls: int = int(_env("MAX_TRANSFERABILITY_CALLS", "8"))
    # How many CVs are processed at once. Each one is mostly waiting on the
    # LLM, so this is bounded by the provider's tokens-per-minute limit, not by
    # CPU cores. A CV extraction is a large request (~7k tokens), so on a free
    # tier even a few at once will be throttled — the default stays modest and
    # the retry logic waits out the limit rather than dropping the candidate.
    ranking_workers: int = int(_env("RANKING_WORKERS", "4"))

    # --- Extraction cache --------------------------------------------------
    # Re-reading an unchanged CV costs tokens and can return a slightly
    # different reading, which makes the same batch rank differently twice.
    # Caching by file content makes re-runs free and reproducible.
    extraction_cache_enabled: bool = _env("EXTRACTION_CACHE", "1") not in ("0", "false", "False", "")
    extraction_cache_dir: str = _env("EXTRACTION_CACHE_DIR", "storage/cache/extractions")

    # --- Scoring -----------------------------------------------------------
    # Fixed by the product specification: equal weighting, 33% each.
    # These are here for transparency and testing, not for tuning away from.
    weight_qualification: float = 1 / 3
    weight_experience: float = 1 / 3
    weight_jd_skills: float = 1 / 3

    # How much an internship / part-time role counts toward "relevant experience".
    # This is an HR policy decision, not a modelling one — confirm with the
    # HR stakeholder before go-live (flagged as an open question in the spec).
    internship_weight: float = float(_env("INTERNSHIP_WEIGHT", "0.5"))
    part_time_weight: float = float(_env("PART_TIME_WEIGHT", "0.6"))

    # A role below this similarity to the JD contributes NO relevant years.
    # Without a floor, a long career in an unrelated field slowly accumulates
    # "relevant" experience through many small similarity values — e.g. seven
    # years of accountancy scoring against an engineering role.
    experience_relevance_floor: float = float(_env("EXPERIENCE_RELEVANCE_FLOOR", "0.35"))

    # How sharply an irrelevant field of study is penalised when the JD names
    # a required field. Higher = stricter. Applied as a multiplier on the
    # level score, so a right-level/wrong-field degree cannot score highly.
    qualification_field_exponent: float = float(_env("QUALIFICATION_FIELD_EXPONENT", "1.5"))
    # Similarity at or above which a field of study counts as a full match.
    qualification_field_full_match: float = float(_env("QUALIFICATION_FIELD_FULL_MATCH", "0.75"))

    # --- Versioning (stamped onto every ranking run for the audit trail) ---
    scoring_engine_version: str = "1.0.0"

    @property
    def weights_sum_to_one(self) -> bool:
        total = self.weight_qualification + self.weight_experience + self.weight_jd_skills
        return abs(total - 1.0) < 1e-9


settings = Settings()
