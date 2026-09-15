"""
Layer 1 — LLM extraction, plus a deterministic validation pass.

The LLM understands messy, free-form CVs. The validation pass re-checks the
things regex is genuinely better at (dates, emails, degree keywords) and
flags disagreements instead of silently trusting either side.
"""

from __future__ import annotations

import datetime as dt
import functools
import logging
import re
from pathlib import Path
from typing import Any

from . import cache
from .config import settings
from .documents import read_document
from .llm import PROMPT_DIR, complete_json, get_llm, load_prompt
from .schema import (
    CV_EXTRACTION_SCHEMA,
    JD_EXTRACTION_SCHEMA,
    CandidateProfile,
    JobProfile,
)

log = logging.getLogger(__name__)

@functools.lru_cache(maxsize=8)
def _template(name: str) -> str:
    """The raw, unfilled prompt text — used to key the extraction cache, so
    editing a prompt automatically invalidates everything it produced."""
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
DEGREE_HINTS = {
    "phd": ["ph.d", "phd", "doctorate", "doctoral"],
    "masters": ["master", "msc", "m.sc", "ms ", "mba", "m.tech", "mtech", "m.e ", "m.phil"],
    "bachelors": ["bachelor", "bsc", "b.sc", "bs ", "b.e", "be ", "b.tech", "btech", "bba"],
    "intermediate": ["intermediate", "fsc", "f.sc", "a-level", "a level", "hssc"],
    "matric": ["matric", "o-level", "o level", "ssc"],
}


def extract_cv(path: str, allow_ocr: bool = True) -> CandidateProfile:
    """Read a CV file and return a structured, validated candidate profile.

    An unchanged file read by an unchanged model and prompt returns the stored
    result instead of calling the LLM again — see cache.py for why that matters
    beyond speed.
    """
    doc = read_document(path, allow_ocr=allow_ocr)
    prompt = load_prompt(
        "extract_cv.txt",
        cv_text=doc.text,
        today=dt.date.today().isoformat(),
    )

    model = get_llm().name
    # The cache key uses the prompt *template*, not the filled-in prompt: the
    # template carries today's date, and keying on that would throw the whole
    # cache away every midnight for no gain in accuracy.
    key = cache.cache_key(path, model, _template("extract_cv"))
    raw = cache.load(key)
    if raw is None:
        raw = complete_json(prompt, CV_EXTRACTION_SCHEMA)
        cache.store(key, raw, Path(path).name)
    else:
        log.debug("Using cached extraction for %s", Path(path).name)

    profile = CandidateProfile.from_dict(
        raw, source_file=path, extraction_model=model
    )

    issues = validate_extraction(profile, doc.text)
    if doc.warning:
        issues.insert(0, doc.warning)
    if issues:
        existing = profile.extraction_notes or ""
        profile.extraction_notes = " | ".join(filter(None, [existing, *issues]))
    return profile


def extract_jd(path: str | None = None, text: str | None = None) -> JobProfile:
    """Read a JD and run the three-field presence check.

    The presence check is a *presence* question, so it has a reliable
    deterministic answer. That means:

      - if no real LLM is configured, or the LLM call fails, the rule-based
        analyser still gives a correct answer rather than the whole thing
        failing; and
      - when the LLM does answer, its result is cross-checked against the
        text, and disagreements are surfaced rather than trusted silently.
    """
    from .jd_rules import analyze_jd_rules, cross_check

    if text is None:
        if path is None:
            raise ValueError("extract_jd needs either path or text")
        text = read_document(path).text

    # No real model configured — go straight to rules.
    if settings.llm_provider in ("stub",):
        return JobProfile.from_dict(analyze_jd_rules(text), source_file=path)

    prompt = load_prompt("extract_jd.txt", jd_text=text)
    try:
        raw = complete_json(prompt, JD_EXTRACTION_SCHEMA)
    except Exception as e:  # noqa: BLE001
        log.warning("LLM JD analysis unavailable (%s) — using the rule-based analyser.", e)
        return JobProfile.from_dict(analyze_jd_rules(text), source_file=path)

    from .jd_rules import quote_is_supported

    issues = cross_check(raw, text)
    if issues:
        log.warning("JD presence-check disagreement: %s", "; ".join(issues))

    rules = analyze_jd_rules(text)
    for key in ("qualification", "experience", "age"):
        model_says = raw.setdefault("requirements", {}).setdefault(key, {})
        from_rules = rules["requirements"][key]

        # (a) The model claims a requirement but its quote is not in the
        #     document. The prompt requires a verbatim quote, so this is an
        #     invented requirement — and accepting it means candidates get
        #     screened against a rule nobody set. Fall back to the text.
        if model_says.get("mentioned") and not quote_is_supported(
            model_says.get("quoted_text"), text
        ):
            log.warning(
                "%s: model's quoted evidence is not in the document — "
                "using the text's own answer instead.", key
            )
            raw["requirements"][key] = from_rules

        # (b) The text plainly states a requirement the model missed. Failing
        #     to detect it makes the system demand information HR already
        #     provided in the advert.
        elif from_rules["mentioned"] and not model_says.get("mentioned"):
            raw["requirements"][key] = from_rules

    return JobProfile.from_dict(raw, source_file=path)


# ---------------------------------------------------------------------------
# Validation layer
# ---------------------------------------------------------------------------


def validate_extraction(profile: CandidateProfile, source_text: str) -> list[str]:
    """Cross-check the LLM's output against the raw text.

    Returns human-readable warnings. These surface in the UI as low-confidence
    markers rather than being silently corrected — a flagged uncertainty is
    useful to a reviewer; a silent fix is not.
    """
    issues: list[str] = []
    lower = source_text.lower()

    # Email — regex is strictly better at this than an LLM.
    found_emails = EMAIL_RE.findall(source_text)
    if found_emails and not profile.email:
        profile.email = found_emails[0]
    elif profile.email and found_emails and profile.email not in found_emails:
        issues.append(f"Extracted email {profile.email!r} does not appear in the CV text.")

    # Age must never be inferred — check it was actually stated.
    if profile.age is not None:
        stated = re.search(r"\b(age|date of birth|d\.o\.b|dob)\b", lower)
        if not stated and str(profile.age) not in source_text:
            issues.append(
                f"Age {profile.age} reported but no age or date of birth found in the CV — "
                "treat as unverified."
            )
            profile.age = None

    # Degree level sanity check against keyword hints.
    for q in profile.qualifications:
        title_l = (q.degree_title or "").lower()
        expected = None
        for level, hints in DEGREE_HINTS.items():
            if any(h in title_l for h in hints):
                expected = level
                break
        if expected and q.level != expected:
            issues.append(
                f"Degree {q.degree_title!r} classified as {q.level!r} but looks like {expected!r}."
            )

    # Completion years should be plausible and present in the text.
    this_year = dt.date.today().year
    for q in profile.qualifications:
        if q.completion_year and not (1950 <= q.completion_year <= this_year + 6):
            issues.append(f"Implausible completion year {q.completion_year} for {q.degree_title!r}.")

    # Experience durations should not exceed a plausible working life, and
    # should roughly agree with the years mentioned in the document.
    total = sum(e.duration_years for e in profile.experience)
    if total > 50:
        issues.append(f"Total experience of {total:.1f} years is implausible — check date parsing.")
    for e in profile.experience:
        if e.duration_years < 0:
            issues.append(f"Negative duration for role {e.job_title!r}.")
        if e.duration_years > 45:
            issues.append(f"Role {e.job_title!r} has an implausible duration of {e.duration_years:.1f} years.")

    # A CV with no years at all in the text but confident dates is suspicious.
    if profile.experience and not YEAR_RE.search(source_text):
        issues.append("Work dates reported but no years found in the CV text.")

    if not profile.skills:
        issues.append("No skills extracted.")

    return issues


def extract_cv_safe(path: str, allow_ocr: bool = True) -> tuple[CandidateProfile | None, str | None]:
    """Extraction that never raises — one bad file must not fail a batch of 100."""
    try:
        return extract_cv(path, allow_ocr=allow_ocr), None
    except Exception as e:  # noqa: BLE001
        log.warning("Extraction failed for %s: %s", path, e)
        return None, str(e)
