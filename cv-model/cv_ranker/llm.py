"""
LLM provider abstraction.

One interface, several backends, so the hosting decision (third-party API vs
self-hosted open-weight model) does not ripple through the codebase. Every
backend returns validated JSON matching a supplied schema.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, **kwargs: Any) -> str:
    """Load a prompt template and fill its placeholders."""
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    return text.format(**kwargs)


class LLMError(RuntimeError):
    pass


class DeterministicFailure(LLMError):
    """A failure that retrying cannot fix — e.g. no fixture matches this input.

    Raised so the retry loop skips straight to the caller's fallback instead of
    repeating an identical lookup and filling the log with noise.
    """


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class BaseLLM:
    name = "base"

    def complete_json(self, prompt: str, schema: dict[str, Any],
                      system: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


class AnthropicLLM(BaseLLM):
    """Uses tool-calling to force schema-valid JSON."""

    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install anthropic") from e
        self._client = anthropic.Anthropic(api_key=settings.llm_api_key or None)
        self.name = settings.llm_model

    def complete_json(self, prompt, schema, system=None):
        resp = self._client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            system=system or "You extract structured data. Always call the provided tool.",
            tools=[{
                "name": "record",
                "description": "Record the extracted structured data.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": "record"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise LLMError("Model did not return the expected tool call")


class OpenAICompatibleLLM(BaseLLM):
    """Works with any OpenAI-compatible endpoint.

    Covers OpenAI, Groq, xAI (Grok), OpenRouter, Together, DeepSeek, vLLM,
    Ollama's shim, TGI — they all speak the same protocol but differ in how
    much of the structured-output spec they implement. So this tries three
    strategies in order and remembers which one worked, rather than assuming:

      1. response_format=json_schema  — strongest, schema enforced by the server
      2. response_format=json_object  — valid JSON guaranteed, shape is not
      3. plain text                   — last resort, schema described in the prompt

    For 2 and 3 the schema is injected into the prompt, so the model still
    knows the target shape.
    """

    def __init__(self, base_url: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install openai") from e
        self._client = OpenAI(
            api_key=settings.llm_api_key or "not-needed",
            base_url=base_url,
            timeout=settings.llm_timeout,
        )
        self.name = settings.llm_model
        self._mode: str | None = None  # cached after the first success

    def _call(self, mode: str, prompt: str, schema: dict[str, Any],
              system: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        user_content = prompt

        if mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "record", "schema": schema, "strict": False},
            }
        else:
            if mode == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            user_content = (
                f"{prompt}\n\n---\n\nReturn ONLY a JSON object matching this schema "
                f"exactly. No markdown, no commentary.\n\n"
                f"{json.dumps(schema, indent=2)}"
            )

        resp = self._client.chat.completions.create(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": system or "You extract structured data as JSON."},
                {"role": "user", "content": user_content},
            ],
            **kwargs,
        )
        return _parse_json(resp.choices[0].message.content or "")

    def complete_json(self, prompt, schema, system=None):
        modes = [self._mode] if self._mode else ["json_schema", "json_object", "plain"]
        last: Exception | None = None
        for mode in modes:
            try:
                result = self._call(mode, prompt, schema, system)
                if self._mode != mode:
                    log.info("Structured-output mode for %s: %s", self.name, mode)
                    self._mode = mode
                return result
            except Exception as e:  # noqa: BLE001
                last = e
                # Only fall through on "this server doesn't support that" style
                # errors — a genuine outage should surface, not be retried three
                # times with weaker settings.
                msg = str(e).lower()
                if not any(k in msg for k in (
                    "response_format", "json_schema", "not supported", "unsupported",
                    "invalid_request", "400", "unrecognized", "unknown parameter",
                )):
                    raise
                log.warning("Mode %r rejected by %s (%s) — trying a weaker mode.",
                            mode, self.name, e)
        raise LLMError(f"No structured-output mode worked for {self.name}: {last}") from last


class StubLLM(BaseLLM):
    """Offline stand-in.

    Returns a minimal schema-shaped object so the pipeline can be exercised
    end-to-end without network access. It does NOT understand CVs — never use
    it for a real ranking.
    """

    name = "stub"

    def complete_json(self, prompt, schema, system=None):
        if "transferability" in prompt.lower()[:200] or "REQUIRED SKILL:" in prompt:
            return {
                "transferability": 0.0,
                "reasoning": "Stub backend — no assessment performed.",
                "evidence": None,
            }
        if "JOB DESCRIPTION TEXT" in prompt:
            return {
                "job_title": "",
                "summary": None,
                "responsibilities_text": None,
                "required_skills": [],
                "preferred_skills": [],
                "requirements": {
                    k: {"mentioned": False, "quoted_text": None, "min_value": None,
                        "max_value": None, "level": None, "field_of_study": None}
                    for k in ("qualification", "experience", "age")
                },
            }
        return {
            "candidate": {"name": "Unknown", "email": None, "phone": None,
                          "location": None, "age": None, "date_of_birth": None},
            "qualifications": [],
            "experience": [],
            "skills": [],
            "certifications": [],
            "languages": [],
            "extraction_notes": "Stub backend — no extraction performed.",
        }


class FixtureLLM(BaseLLM):
    """Replays pre-recorded extraction output from data/fixtures/*.json.

    Lets the whole pipeline — matching, scoring, ranking, blocking rules — be
    run and regression-tested without an API key. Each fixture declares a
    `match` string; the fixture whose string appears in the prompt is used.
    """

    name = "fixture"

    def __init__(self, fixture_dir: str | Path = "data/fixtures") -> None:
        self._fixtures: list[tuple[str, dict[str, Any]]] = []
        d = Path(fixture_dir)
        if d.exists():
            for f in sorted(d.glob("*.json")):
                data = json.loads(f.read_text(encoding="utf-8"))
                self._fixtures.append((data["match"], data["output"]))
        if not self._fixtures:
            log.warning("No fixtures found in %s — run: python make_fixtures.py", d)

    def complete_json(self, prompt, schema, system=None):
        if "REQUIRED SKILL:" in prompt:
            # Transferability is a judgement call; without a real model we
            # decline rather than inventing a score.
            return {
                "transferability": 0.0,
                "reasoning": "Fixture backend — no transferability assessment available.",
                "evidence": None,
            }
        haystack = prompt.replace("\r\n", "\n")
        for needle, output in self._fixtures:
            if needle in haystack:
                return output
        raise DeterministicFailure(
            "No fixture matched this document. Add one to data/fixtures/, or "
            "configure a real LLM_PROVIDER."
        )


def _parse_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parse — strips markdown fences some models add."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise LLMError(f"Could not parse JSON from model output: {e}") from e


# Convenience presets so the base URL doesn't have to be remembered.
PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "grok": "https://api.x.ai/v1",          # xAI
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

_BACKENDS = {
    "anthropic": lambda: AnthropicLLM(),
    "openai": lambda: OpenAICompatibleLLM(base_url=None),
    # Any OpenAI-compatible endpoint; base URL from LLM_BASE_URL.
    "openai_compatible": lambda: OpenAICompatibleLLM(base_url=settings.llm_base_url),
    "ollama": lambda: OpenAICompatibleLLM(base_url=settings.llm_base_url),
    # Hosted presets — no base URL needed.
    **{
        name: (lambda url=url: OpenAICompatibleLLM(base_url=url))
        for name, url in PROVIDER_BASE_URLS.items()
    },
    "fixture": lambda: FixtureLLM(),
    "stub": lambda: StubLLM(),
}

_client: BaseLLM | None = None


def get_llm() -> BaseLLM:
    global _client
    if _client is None:
        factory = _BACKENDS.get(settings.llm_provider)
        if factory is None:
            raise LLMError(
                f"Unknown LLM_PROVIDER {settings.llm_provider!r}. "
                f"Options: {', '.join(_BACKENDS)}"
            )
        _client = factory()
        log.info("LLM backend: %s (%s)", settings.llm_provider, _client.name)
    return _client


_RETRY_AFTER_RE = re.compile(r"(?:try again in|retry after)\s*([0-9smhd.\s]+)", re.IGNORECASE)
# Durations arrive compound and unspaced: "19.5225s", "23m25.296s", "1h2m3s",
# "250ms". Reading only the first number turns 23 minutes into 23 seconds, and
# the caller then treats a spent daily quota as a blip worth retrying.
_DURATION_PART_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m|h|d)?", re.IGNORECASE)
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0, "": 1.0}


def _parse_duration(text: str) -> float | None:
    """Total seconds in a duration like '23m25.296s'. None if unparseable."""
    total = 0.0
    found = False
    for value, unit in _DURATION_PART_RE.findall(text.strip()):
        try:
            total += float(value) * _UNIT_SECONDS[unit.lower()]
        except (ValueError, KeyError):
            continue
        found = True
    return total if found else None


class QuotaExhausted(LLMError):
    """The provider's quota is gone for a period too long to wait out.

    Separate from a plain rate limit because the right response is different:
    a per-minute limit clears in seconds and is worth waiting for, but a daily
    quota does not come back today. Retrying that only burns time and still
    drops the candidate — with a message about "rate limits" that reads like a
    transient glitch, when the real answer is "the key is out of budget".
    """


def _rate_limit_wait(err: Exception) -> float | None:
    """Seconds to wait for a rate-limit error, or None if it isn't one.

    Providers state exactly how long to wait ("Please try again in 7.545s").
    Exponential backoff ignores that and retries far too early, so the call
    burns its attempts and the CV is dropped from the ranking — a candidate
    silently missing from a shortlist is the worst failure this system has.
    Honouring the stated delay turns a lost candidate into a slow one.

    Raises QuotaExhausted when the stated delay is longer than we are willing
    to hold a ranking open for.
    """
    msg = str(err)
    if not any(k in msg.lower() for k in ("rate limit", "rate_limit", "429", "too many requests")):
        return None

    m = _RETRY_AFTER_RE.search(msg)
    value = _parse_duration(m.group(1)) if m else None
    if value is None:
        return 20.0  # rate-limited but no hint given — wait out a typical window

    if value > settings.llm_rate_limit_max_wait:
        per_day = "per day" in msg.lower() or "tpd" in msg.lower()
        raise QuotaExhausted(
            f"{'Daily' if per_day else 'Rate'} quota exhausted — the provider asks to wait "
            f"{value / 60:.0f} minute(s), which is too long to hold a ranking open. "
            f"{'The daily allowance resets tomorrow. ' if per_day else ''}"
            f"Use a self-hosted model (LLM_PROVIDER=ollama) or a paid tier to continue now."
        ) from err
    return value + 1.0  # a second of headroom


def complete_json(prompt: str, schema: dict[str, Any], system: str | None = None,
                  retries: int = 2) -> dict[str, Any]:
    """Call the configured LLM, retrying transient failures with backoff.

    Rate limits get their own, more patient budget: they are not failures, they
    are the provider asking us to slow down, and the answer will be there if we
    wait. Everything else keeps the short exponential backoff.
    """
    llm = get_llm()
    last: Exception | None = None
    attempt = 0
    rate_limit_retries = 0
    max_rate_limit_retries = 5

    while True:
        try:
            return llm.complete_json(prompt, schema, system)
        except (DeterministicFailure, QuotaExhausted):
            raise  # retrying is pointless; let the caller fall back
        except Exception as e:  # noqa: BLE001 - deliberately broad; providers differ
            last = e
            wait = _rate_limit_wait(e)  # may raise QuotaExhausted
            if wait is not None:
                if rate_limit_retries >= max_rate_limit_retries:
                    raise LLMError(
                        f"Rate limited by {llm.name} after {rate_limit_retries} waits. "
                        f"Lower RANKING_WORKERS or MAX_TRANSFERABILITY_CALLS, or move to a "
                        f"higher tier: {e}"
                    ) from e
                rate_limit_retries += 1
                log.warning("Rate limited — waiting %.1fs before retry %d/%d.",
                            wait, rate_limit_retries, max_rate_limit_retries)
                time.sleep(wait)
                continue  # a rate limit does not consume a normal attempt
            if attempt >= retries:
                break
            wait = 2 ** attempt
            attempt += 1
            log.warning("LLM call failed (%s), retrying in %ss", e, wait)
            time.sleep(wait)

    raise LLMError(f"LLM call failed after {attempt + 1} attempts: {last}") from last
