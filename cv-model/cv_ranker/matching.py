"""
Semantic skill and experience matching.

Three tiers, cheapest first:

  1. Embedding similarity  >= skill_match_threshold  -> direct match, free.
  2. Embedding similarity in the middle band          -> ask the LLM whether
     the competence transfers, and get a written justification.
  3. Embedding similarity below consider_threshold    -> unrelated, no call.

Tier 2 is what handles "worked on a different tech stack but it transfers".
Tier 1 is what handles "wrote the same skill differently".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .config import settings
from .embeddings import cosine_matrix, embed_texts
from .llm import complete_json, load_prompt
from .schema import CandidateProfile, JobProfile

log = logging.getLogger(__name__)

TRANSFERABILITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["transferability", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "transferability": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
        "evidence": {"type": ["string", "null"]},
    },
}


@dataclass
class SkillMatch:
    required_skill: str
    matched_skill: Optional[str]
    similarity: float
    credit: float           # 0..1 contribution toward the skills score
    method: str             # "direct" | "transferable" | "none"
    reasoning: Optional[str] = None
    evidence: Optional[str] = None

    @property
    def is_matched(self) -> bool:
        return self.credit >= 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_skill": self.required_skill,
            "matched_skill": self.matched_skill,
            "similarity": round(self.similarity, 3),
            "credit": round(self.credit, 3),
            "method": self.method,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
        }


@dataclass
class ExperienceRelevance:
    job_title: str
    employer: Optional[str]
    duration_years: float
    employment_type: str
    relevance: float        # 0..1 semantic similarity to the JD
    weighted_years: float   # duration x relevance x employment-type weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_title": self.job_title,
            "employer": self.employer,
            "duration_years": round(self.duration_years, 2),
            "employment_type": self.employment_type,
            "relevance": round(self.relevance, 3),
            "weighted_years": round(self.weighted_years, 2),
        }


@dataclass
class MatchResult:
    skill_matches: list[SkillMatch] = field(default_factory=list)
    experience_relevance: list[ExperienceRelevance] = field(default_factory=list)
    relevant_years: float = 0.0
    jd_similarity: float = 0.0   # whole-CV vs whole-JD semantic similarity

    @property
    def matched_skills(self) -> list[str]:
        return [m.required_skill for m in self.skill_matches if m.is_matched]

    @property
    def missing_skills(self) -> list[str]:
        return [m.required_skill for m in self.skill_matches if not m.is_matched]


# ---------------------------------------------------------------------------


def _employment_weight(employment_type: str) -> float:
    """How much a role counts toward 'relevant experience'.

    This encodes an HR policy decision, not a modelling one — the values live
    in config so HR can set them without touching code.
    """
    return {
        "internship": settings.internship_weight,
        "part_time": settings.part_time_weight,
    }.get(employment_type, 1.0)


def _candidate_evidence_text(candidate: CandidateProfile, near_skills: list[str]) -> str:
    """Compact evidence bundle for the transferability prompt."""
    lines = []
    if near_skills:
        lines.append("Related skills listed: " + ", ".join(near_skills))
    if candidate.skills:
        lines.append("All skills listed: " + ", ".join(candidate.skills[:40]))
    lines.append("")
    lines.append("Work history:")
    for e in candidate.experience[:6]:
        lines.append(
            f"- {e.job_title} at {e.employer or 'unspecified'} "
            f"({e.duration_years:.1f} yrs, {e.employment_type}): {e.description[:400]}"
        )
    return "\n".join(lines)


def match_skills(candidate: CandidateProfile, job: JobProfile,
                 use_llm_transferability: bool = True) -> list[SkillMatch]:
    """Match each required skill against the candidate's skills semantically."""
    required = [s for s in job.required_skills if s and s.strip()]
    if not required:
        return []

    cand_skills = [s for s in candidate.skills if s and s.strip()]
    # Role technologies are skills too, even if not in a skills section.
    for e in candidate.experience:
        cand_skills.extend(t for t in e.technologies if t and t.strip())
    cand_skills = list(dict.fromkeys(cand_skills))  # de-dupe, keep order

    if not cand_skills:
        return [SkillMatch(r, None, 0.0, 0.0, "none") for r in required]

    req_vecs = embed_texts(required)
    cand_vecs = embed_texts(cand_skills)
    sims = cosine_matrix(req_vecs, cand_vecs)  # (n_required, n_candidate)

    results: list[SkillMatch] = []
    llm_budget = settings.max_transferability_calls

    for i, req in enumerate(required):
        row = sims[i]
        best_idx = int(np.argmax(row))
        best_sim = float(row[best_idx])
        best_skill = cand_skills[best_idx]

        # Tier 1 — same thing, differently written.
        if best_sim >= settings.skill_match_threshold:
            results.append(SkillMatch(
                required_skill=req,
                matched_skill=best_skill,
                similarity=best_sim,
                credit=1.0,
                method="direct",
                reasoning=f"Matched to “{best_skill}” (similarity {best_sim:.2f}).",
            ))
            continue

        # Tier 3 — nothing close enough to be worth an LLM call.
        if best_sim < settings.skill_consider_threshold or not use_llm_transferability:
            results.append(SkillMatch(req, None, best_sim, 0.0, "none"))
            continue

        # Tier 2 — the interesting middle: different tool, possibly transferable.
        if llm_budget <= 0:
            results.append(SkillMatch(req, None, best_sim, 0.0, "none",
                                      reasoning="Transferability budget exhausted."))
            continue

        near_idx = np.argsort(-row)[:5]
        near_skills = [cand_skills[j] for j in near_idx
                       if row[j] >= settings.skill_consider_threshold]
        prompt = load_prompt(
            "transferability.txt",
            required_skill=req,
            candidate_evidence=_candidate_evidence_text(candidate, near_skills),
        )
        try:
            out = complete_json(prompt, TRANSFERABILITY_SCHEMA)
            llm_budget -= 1
            credit = float(out.get("transferability", 0.0))
            results.append(SkillMatch(
                required_skill=req,
                matched_skill=near_skills[0] if near_skills else None,
                similarity=best_sim,
                credit=max(0.0, min(1.0, credit)),
                method="transferable",
                reasoning=out.get("reasoning"),
                evidence=out.get("evidence"),
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("Transferability check failed for %r: %s", req, e)
            results.append(SkillMatch(req, None, best_sim, 0.0, "none",
                                      reasoning="Transferability check unavailable."))

    return results


def score_experience_relevance(candidate: CandidateProfile,
                               job: JobProfile) -> tuple[list[ExperienceRelevance], float]:
    """Weight each past role by how relevant it is to this JD.

    This is what makes 'relevant experience' different from 'total years':
    five years in a closely-related role counts far more than five unrelated.
    """
    if not candidate.experience:
        return [], 0.0

    jd_text = " ".join(filter(None, [
        job.job_title,
        job.summary,
        job.responsibilities_text,
        ", ".join(job.required_skills),
    ])).strip() or job.job_title

    role_texts = [
        f"{e.job_title}. {e.description} {' '.join(e.technologies)}".strip()
        for e in candidate.experience
    ]

    jd_vec = embed_texts([jd_text])
    role_vecs = embed_texts(role_texts)
    sims = cosine_matrix(jd_vec, role_vecs)[0]

    out: list[ExperienceRelevance] = []
    total = 0.0
    for e, sim in zip(candidate.experience, sims):
        relevance = max(0.0, float(sim))
        # Below the floor the role is treated as unrelated and contributes
        # nothing, so a long career in another field cannot accumulate
        # "relevant" years through many small similarity values.
        if relevance < settings.experience_relevance_floor:
            weighted = 0.0
        else:
            weighted = e.duration_years * relevance * _employment_weight(e.employment_type)
        total += weighted
        out.append(ExperienceRelevance(
            job_title=e.job_title,
            employer=e.employer,
            duration_years=e.duration_years,
            employment_type=e.employment_type,
            relevance=relevance,
            weighted_years=weighted,
        ))
    return out, total


def match(candidate: CandidateProfile, job: JobProfile,
          use_llm_transferability: bool = True) -> MatchResult:
    skill_matches = match_skills(candidate, job, use_llm_transferability)
    exp_rel, relevant_years = score_experience_relevance(candidate, job)

    # Whole-document similarity, used as a smoothing signal in the skills score
    # so a candidate whose CV is clearly on-topic isn't punished purely for
    # wording their skills list differently.
    cv_blob = " ".join([
        " ".join(candidate.skills),
        " ".join(f"{e.job_title} {e.description}" for e in candidate.experience),
        " ".join(q.degree_title for q in candidate.qualifications),
    ]).strip()
    jd_blob = " ".join(filter(None, [
        job.job_title, job.summary, job.responsibilities_text,
        ", ".join(job.required_skills),
    ])).strip()

    jd_sim = 0.0
    if cv_blob and jd_blob:
        vecs = embed_texts([cv_blob, jd_blob])
        jd_sim = max(0.0, float(cosine_matrix(vecs[0], vecs[1])[0][0]))

    return MatchResult(
        skill_matches=skill_matches,
        experience_relevance=exp_rel,
        relevant_years=relevant_years,
        jd_similarity=jd_sim,
    )
