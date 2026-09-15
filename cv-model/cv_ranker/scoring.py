"""
Deterministic scoring engine.

Everything semantic already happened in matching.py. What is left here is
arithmetic, and it is deliberately deterministic: the same inputs must always
produce the same score, or the audit trail is worthless and HR cannot trust
that a candidate's number is stable.

Final score = equal-weighted mean of three sub-scores (33% each), per the
product specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .config import settings
from .embeddings import cosine_matrix, embed_texts
from .matching import MatchResult
from .schema import CandidateProfile, JobProfile

# Ordinal ranking of academic level. This is a numeric fact, not a language
# problem — no model needed. Whether a *field* of study is relevant IS a
# language problem and is handled semantically below.
LEVEL_RANK = {
    "unknown": 0,
    "certification": 1,
    "matric": 1,
    "intermediate": 2,
    "diploma": 3,
    "bachelors": 4,
    "masters": 5,
    "mphil": 6,
    "phd": 7,
}


@dataclass
class SubScore:
    value: float                      # 0..100
    explanation: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateScore:
    candidate_name: str
    qualification: SubScore
    experience: SubScore
    jd_skills: SubScore
    final: float
    # Contact details, carried through from the CV.
    #
    # These are read out of the document by the extractor and were then thrown
    # away here, so a reviewer looking at a shortlist had a ranked list of
    # people and no way to reach any of them without reopening the files. They
    # take no part in scoring and never will: a score that moved because of
    # somebody's address would be indefensible.
    email: Optional[str] = None
    phone: Optional[str] = None
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    source_file: Optional[str] = None
    # Stamped for the audit trail — which versions produced this number.
    scoring_engine_version: str = settings.scoring_engine_version
    extraction_model: Optional[str] = None
    embedding_model: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "email": self.email,
            "phone": self.phone,
            "final_score": round(self.final, 1),
            "scores": {
                "qualification": round(self.qualification.value, 1),
                "experience": round(self.experience.value, 1),
                "jd_skills": round(self.jd_skills.value, 1),
            },
            "explanations": {
                "qualification": self.qualification.explanation,
                "experience": self.experience.explanation,
                "jd_skills": self.jd_skills.explanation,
            },
            "details": {
                "qualification": self.qualification.details,
                "experience": self.experience.details,
                "jd_skills": self.jd_skills.details,
            },
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "flags": self.flags,
            "source_file": self.source_file,
            "versions": {
                "scoring_engine": self.scoring_engine_version,
                "extraction_model": self.extraction_model,
                "embedding_model": self.embedding_model,
            },
        }


# ---------------------------------------------------------------------------
# 1. Qualification
# ---------------------------------------------------------------------------


def score_qualification(candidate: CandidateProfile, job: JobProfile) -> SubScore:
    req = job.effective("qualification")
    required_level = (req.get("level") or "").lower()
    required_field = req.get("field_of_study") or ""
    req_text = req.get("text") or ""

    if not candidate.qualifications:
        return SubScore(0.0, "No qualification found on the CV.", {"requirement": req_text})

    # Best (highest) qualification the candidate holds.
    best = max(candidate.qualifications, key=lambda q: LEVEL_RANK.get(q.level, 0))
    cand_rank = LEVEL_RANK.get(best.level, 0)
    req_rank = LEVEL_RANK.get(required_level, 0)

    # --- Level component (deterministic, ordinal) ---
    if req_rank == 0:
        level_score = 70.0  # no level stated; neutral rather than punitive
        level_note = "No specific level required."
    elif cand_rank >= req_rank:
        # Meeting the requirement is full marks. Exceeding it adds a little,
        # but is deliberately capped — a PhD is not automatically a better
        # hire for a role asking for a bachelor's.
        level_score = min(100.0, 100.0 + 0.0 * (cand_rank - req_rank))
        level_note = f"{best.degree_title} meets the required level."
    else:
        gap = req_rank - cand_rank
        level_score = max(0.0, 100.0 - 30.0 * gap)
        level_note = f"{best.degree_title} is below the required level."

    # --- Field relevance (semantic, NOT a lookup table) ---
    # Applied as a MULTIPLIER on the level score, not averaged with it. A
    # degree at the right level in an unrelated field should not inherit a
    # high score just for being a bachelor's — averaging would floor an
    # irrelevant degree at 60%, which is wrong.
    if required_field.strip():
        cand_field_text = f"{best.degree_title} {best.field_of_study}".strip()
        vecs = embed_texts([cand_field_text, required_field])
        field_sim = max(0.0, float(cosine_matrix(vecs[0], vecs[1])[0][0]))
        normalised = min(1.0, field_sim / settings.qualification_field_full_match)
        field_factor = normalised ** settings.qualification_field_exponent
        field_score = round(field_factor * 100.0, 1)
        field_note = (
            f"Field “{best.field_of_study}” vs required “{required_field}” "
            f"(similarity {field_sim:.2f})."
        )
    else:
        field_factor = 1.0
        field_score = level_score
        field_note = "No specific field of study required."

    value = level_score * field_factor
    if not best.is_completed:
        value *= 0.85
        field_note += " Qualification not yet completed."

    return SubScore(
        value=round(min(100.0, max(0.0, value)), 1),
        explanation=f"{best.degree_title} — required: {req_text or 'not specified'}. "
                    f"{level_note} {field_note}",
        details={
            "candidate_qualification": best.degree_title,
            "candidate_level": best.level,
            "required_level": required_level or None,
            "required_field": required_field or None,
            "requirement_source": req.get("source"),
            "level_score": round(level_score, 1),
            "field_score": round(field_score, 1),
        },
    )


# ---------------------------------------------------------------------------
# 2. Relevant experience
# ---------------------------------------------------------------------------


def score_experience(candidate: CandidateProfile, job: JobProfile,
                     m: MatchResult) -> SubScore:
    req = job.effective("experience")
    req_min = req.get("min_value")
    req_max = req.get("max_value")
    req_text = req.get("text") or ""

    relevant = m.relevant_years
    total = sum(e.duration_years for e in candidate.experience)

    if req_min is None:
        # No numeric requirement — score on relevance density instead of a
        # threshold, so this degrades gracefully rather than defaulting to 0.
        density = (relevant / total) if total > 0 else 0.0
        value = min(100.0, 40.0 * relevant + 40.0 * density)
        note = "No numeric experience requirement stated; scored on relevant experience found."
    else:
        req_min = float(req_min)
        if req_min <= 0:
            value = 100.0
            note = "Role open to candidates with no prior experience."
        else:
            ratio = relevant / req_min
            if ratio >= 1.0:
                value = 100.0
                note = "Meets the required relevant experience."
            else:
                value = max(0.0, ratio * 100.0)
                note = "Below the required relevant experience."
        # Being far over an explicit upper bound is a mild signal of
        # over-qualification, not a disqualifier.
        if req_max and relevant > float(req_max) * 1.5:
            value *= 0.9
            note += " Substantially above the stated range."

    return SubScore(
        value=round(min(100.0, max(0.0, value)), 1),
        explanation=(
            f"{relevant:.1f} relevant years (of {total:.1f} total) — "
            f"required: {req_text or 'not specified'}. {note}"
        ),
        details={
            "relevant_years": round(relevant, 2),
            "total_years": round(total, 2),
            "required_min": req_min,
            "required_max": req_max,
            "requirement_source": req.get("source"),
            "roles": [r.to_dict() for r in m.experience_relevance],
        },
    )


# ---------------------------------------------------------------------------
# 3. JD & skills
# ---------------------------------------------------------------------------


def score_jd_skills(candidate: CandidateProfile, job: JobProfile,
                    m: MatchResult) -> SubScore:
    if not m.skill_matches:
        value = m.jd_similarity * 100.0
        return SubScore(
            round(value, 1),
            f"No required skills listed; scored on overall CV/JD similarity ({m.jd_similarity:.2f}).",
            {"jd_similarity": round(m.jd_similarity, 3), "skill_matches": []},
        )

    # Credit is fractional: direct matches score 1.0, transferable skills score
    # what the LLM judged (e.g. 0.7 for Vue against a React requirement).
    credit = sum(sm.credit for sm in m.skill_matches) / len(m.skill_matches)

    # Blend with whole-document similarity so a clearly on-topic CV isn't
    # punished purely for listing its skills in unusual wording.
    value = (0.75 * credit + 0.25 * m.jd_similarity) * 100.0

    n_direct = sum(1 for sm in m.skill_matches if sm.method == "direct")
    n_transfer = sum(1 for sm in m.skill_matches if sm.method == "transferable" and sm.credit > 0)

    return SubScore(
        value=round(min(100.0, max(0.0, value)), 1),
        explanation=(
            f"Matched {n_direct} of {len(m.skill_matches)} required skills directly"
            + (f", {n_transfer} as transferable" if n_transfer else "")
            + f". Overall CV/JD similarity {m.jd_similarity:.2f}."
        ),
        details={
            "jd_similarity": round(m.jd_similarity, 3),
            "average_credit": round(credit, 3),
            "skill_matches": [sm.to_dict() for sm in m.skill_matches],
        },
    )


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------


def score_candidate(candidate: CandidateProfile, job: JobProfile,
                    m: MatchResult, embedding_model: str | None = None) -> CandidateScore:
    q = score_qualification(candidate, job)
    e = score_experience(candidate, job, m)
    s = score_jd_skills(candidate, job, m)

    final = (
        settings.weight_qualification * q.value
        + settings.weight_experience * e.value
        + settings.weight_jd_skills * s.value
    )

    flags: list[str] = []
    if candidate.extraction_notes:
        flags.append(f"Extraction note: {candidate.extraction_notes}")
    if not candidate.qualifications:
        flags.append("No qualifications extracted — check the CV parsed correctly.")
    if not candidate.experience:
        flags.append("No work history extracted — check the CV parsed correctly.")

    # Age is checked for eligibility but deliberately does NOT feed the score.
    # It is reported for the human reviewer to apply, because age-based
    # screening is a policy decision a person should make explicitly.
    age_req = job.effective("age")
    if candidate.age is not None and age_req.get("min_value") is not None:
        lo = float(age_req["min_value"])
        hi = float(age_req["max_value"]) if age_req.get("max_value") else None
        if candidate.age < lo or (hi and candidate.age > hi):
            flags.append(
                f"Age {candidate.age} is outside the stated requirement "
                f"({age_req.get('text') or f'{lo:g}–{hi:g}'}) — for reviewer judgement."
            )

    return CandidateScore(
        candidate_name=candidate.name,
        email=candidate.email,
        phone=candidate.phone,
        qualification=q,
        experience=e,
        jd_skills=s,
        final=round(final, 1),
        matched_skills=m.matched_skills,
        missing_skills=m.missing_skills,
        flags=flags,
        source_file=candidate.source_file,
        extraction_model=candidate.extraction_model,
        embedding_model=embedding_model,
    )


def rank(scores: list[CandidateScore], top_n: int | None = None) -> list[CandidateScore]:
    """Sort by final score, descending. Ties broken deterministically by name
    so repeated runs produce identical ordering."""
    ordered = sorted(scores, key=lambda s: (-s.final, s.candidate_name))
    return ordered[:top_n] if top_n else ordered
