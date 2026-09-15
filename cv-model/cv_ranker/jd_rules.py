"""
Rule-based job-description analyser.

The three-field presence check is a *presence* question, not an
interpretation one: does this document state a requirement for age,
experience and qualification? That is exactly the kind of question regex and
keyword matching answer reliably and cheaply — no model needed, no API key,
fully deterministic, and it quotes the source sentence back as evidence.

This runs as:
  - the fallback whenever the configured LLM cannot handle a JD
    (e.g. fixture mode, or an API failure), and
  - a cross-check on the LLM's answer, so a hallucinated "mentioned: true"
    on a field that is not in the text gets caught.

Skill extraction and CV parsing are NOT done here — those genuinely need a
model, because they depend on meaning rather than presence.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Patterns, ordered most-specific first so the best evidence wins.
# ---------------------------------------------------------------------------

AGE_PATTERNS = [
    r"\bage\s*(?:limit|requirement|range|criteria|bracket)?\s*[:\-–]\s*[^\n]{0,60}",
    r"\b\d{2}\s*(?:-|–|—|to)\s*\d{2}\s*years?\s*(?:of\s*age|old)\b",
    r"\bbetween\s+\d{2}\s+and\s+\d{2}\s+years\s+of\s+age\b",
    r"\b(?:max(?:imum)?|min(?:imum)?|under|below|above|over)\s+age\b[^\n]{0,50}",
    r"\bnot\s+(?:more|older|younger)\s+than\s+\d{2}\s*(?:years)?\b",
    r"\byears?\s+of\s+age\b",
    r"\bdate\s+of\s+birth\b",
    r"\bage\s+should\s+be\b[^\n]{0,50}",
]

EXPERIENCE_PATTERNS = [
    r"\bexperience\s*[:\-–]\s*[^\n]{0,80}",
    r"\b\d+\s*(?:\+|plus)?\s*(?:-|–|—|to)?\s*\d*\s*years?['’]?\s*(?:of\s+)?"
    r"(?:relevant\s+|professional\s+|work\s+|industry\s+|post[- ]qualification\s+)?experience\b",
    r"\b(?:minimum|at\s+least|no\s+less\s+than)\s+\d+\s+years?\b[^\n]{0,50}",
    r"\bfresh\s+graduates?\b[^\n]{0,40}",
    r"\bno\s+prior\s+experience\b[^\n]{0,40}",
    r"\bentry[- ]level\b",
    r"\bexperience\b",
]

QUALIFICATION_PATTERNS = [
    r"\b(?:qualification|education|academic\s+requirement)s?\s*[:\-–]\s*[^\n]{0,100}",
    r"\b(?:bachelor|master|doctorate|phd)[^\n]{0,80}",
    r"\b(?:bs|ms|b\.?sc|m\.?sc|b\.?e|m\.?e|b\.?tech|m\.?tech|bba|mba|acca|acma|ca|cfa|cima|icma)\b"
    r"[^\n]{0,80}",
    r"\bdegree\s+in\b[^\n]{0,60}",
    r"\bdiploma\s+in\b[^\n]{0,60}",
    r"\bgraduate\s+(?:in|of|from)\b[^\n]{0,60}",
]

# Level keywords -> normalised enum. Longest/most specific first.
LEVEL_KEYWORDS: list[tuple[str, str]] = [
    (r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctoral\b", "phd"),
    (r"\bm\.?phil\b", "mphil"),
    (r"\bmaster'?s?\b|\bm\.?sc\b|\bmsc\b|\bm\.?tech\b|\bmba\b|\bm\.?e\b|\bms\b", "masters"),
    (r"\bacca\b|\bacma\b|\bcima\b|\bicma\b|\bcfa\b|\bca\b|\bcpa\b", "certification"),
    (r"\bbachelor'?s?\b|\bb\.?sc\b|\bbsc\b|\bb\.?tech\b|\bbba\b|\bb\.?e\b|\bbs\b", "bachelors"),
    (r"\bdiploma\b", "diploma"),
    (r"\bintermediate\b|\bf\.?sc\b|\bfsc\b|\ba-?levels?\b|\bhssc\b", "intermediate"),
    (r"\bmatric\b|\bo-?levels?\b|\bssc\b", "matric"),
]


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[•\-\*•\d.]+\s*", "", s)
    return s.rstrip(" .,;:")


def _find(text: str, patterns: list[str]) -> Optional[str]:
    """Return the cleaned sentence containing the first match, as evidence."""
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        # Widen to the surrounding line so the quote reads naturally.
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        snippet = _clean(text[line_start:line_end])
        if not snippet:
            snippet = _clean(m.group(0))
        return snippet[:200]
    return None


def _numeric_range(snippet: str) -> tuple[Optional[float], Optional[float]]:
    """Pull a numeric range out of an evidence snippet."""
    if not snippet:
        return None, None
    low = snippet.lower()
    if re.search(r"\bfresh\s+graduate|no\s+prior\s+experience|entry[- ]level\b", low):
        return 0.0, None
    rng = re.search(r"\b(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\b", snippet)
    if rng:
        return float(rng.group(1)), float(rng.group(2))
    plus = re.search(r"\b(\d{1,2})\s*(?:\+|plus)", snippet)
    if plus:
        return float(plus.group(1)), None
    at_least = re.search(r"\b(?:minimum|at\s+least|no\s+less\s+than|min\.?)\s*(\d{1,2})\b", low)
    if at_least:
        return float(at_least.group(1)), None
    single = re.search(r"\b(\d{1,2})\s*years?\b", low)
    if single:
        return float(single.group(1)), None
    return None, None


def _level(snippet: str) -> Optional[str]:
    if not snippet:
        return None
    for pattern, level in LEVEL_KEYWORDS:
        if re.search(pattern, snippet, re.IGNORECASE):
            return level
    return None


def _field_of_study(snippet: str) -> Optional[str]:
    if not snippet:
        return None
    m = re.search(r"\b(?:degree|qualification|graduate)\s+in\s+([^\n,;.()]{3,60})", snippet, re.I)
    if m:
        return _clean(m.group(1))
    m = re.search(r"\bin\s+([A-Z][A-Za-z/&\- ]{3,50})", snippet)
    if m:
        return _clean(m.group(1))
    return None


def _job_title(text: str) -> str:
    m = re.search(r"\b(?:position\s+title|job\s+title|position|role)\s*[:\-–]\s*([^\n]{3,80})",
                  text, re.IGNORECASE)
    if m:
        return _clean(m.group(1))
    # Otherwise: first non-boilerplate line that looks like a title.
    for line in text.splitlines():
        c = _clean(line)
        if 3 < len(c) < 80 and not re.match(r"^(about|we\s|the\s)", c, re.I):
            return c
    return ""


def _responsibilities(text: str) -> Optional[str]:
    m = re.search(
        r"(?:key\s+)?(?:responsibilities|duties|role\s+summary|position\s+summ\w+|job\s+description)"
        r"\s*[:\-–]?\s*\n(.{50,2500}?)(?:\n\s*\n[A-Z][^\n]{0,40}[:\-–]\s*\n|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    return _clean(m.group(1))[:2000] if m else None


def _requirement(text: str, patterns: list[str], numeric: bool,
                 with_level: bool = False) -> dict[str, Any]:
    snippet = _find(text, patterns)
    out: dict[str, Any] = {
        "mentioned": snippet is not None,
        "quoted_text": snippet,
        "min_value": None,
        "max_value": None,
        "level": None,
        "field_of_study": None,
    }
    if snippet and numeric:
        out["min_value"], out["max_value"] = _numeric_range(snippet)
    if snippet and with_level:
        out["level"] = _level(snippet)
        out["field_of_study"] = _field_of_study(snippet)
    return out


def analyze_jd_rules(text: str) -> dict[str, Any]:
    """Deterministic JD analysis. Same output shape as the LLM extractor."""
    return {
        "job_title": _job_title(text),
        "summary": None,
        "responsibilities_text": _responsibilities(text),
        "required_skills": [],   # meaning-dependent: left to the model or the user
        "preferred_skills": [],
        "requirements": {
            "qualification": _requirement(text, QUALIFICATION_PATTERNS, False, with_level=True),
            "experience": _requirement(text, EXPERIENCE_PATTERNS, True),
            "age": _requirement(text, AGE_PATTERNS, True),
        },
    }


def _normalise(s: str) -> str:
    """Loose form for comparing a quote against the source document."""
    s = re.sub(r"[\s ]+", " ", s.lower())
    s = re.sub(r"[^\w %/&+.\-–—:]", "", s)
    return s.strip()


def quote_is_supported(quote: Optional[str], text: str) -> bool:
    """Does this quoted evidence actually appear in the document?

    The prompt requires `quoted_text` to be copied verbatim, so a quote that
    is not in the source means the requirement was invented. Compared loosely
    (whitespace, punctuation, bullet characters) because extraction from PDF
    and DOCX mangles those.
    """
    if not quote or not quote.strip():
        return False
    q, t = _normalise(quote), _normalise(text)
    if q in t:
        return True
    # Fall back to substantial word overlap for lightly reworded quotes.
    words = [w for w in q.split() if len(w) > 3]
    if not words:
        return False
    hits = sum(1 for w in words if w in t)
    return hits / len(words) >= 0.8


def cross_check(llm_result: dict[str, Any], text: str) -> list[str]:
    """Compare an LLM's presence check against the rule-based one.

    Disagreements are reported, not silently corrected — a flagged
    uncertainty is useful to a reviewer; a silent override is not.
    One direction matters more than the other: an LLM claiming a requirement
    exists when the text does not contain it means candidates get screened
    against a rule nobody set.
    """
    rules = analyze_jd_rules(text)
    issues: list[str] = []
    for key in ("qualification", "experience", "age"):
        llm_says = bool((llm_result.get("requirements", {}).get(key) or {}).get("mentioned"))
        rules_say = bool(rules["requirements"][key]["mentioned"])
        if llm_says and not rules_say:
            issues.append(
                f"{key}: model reported this requirement but no supporting text was found."
            )
        elif rules_say and not llm_says:
            issues.append(
                f"{key}: text appears to mention this "
                f"(“{rules['requirements'][key]['quoted_text']}”) but the model did not report it."
            )
    return issues
