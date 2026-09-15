"""
End-to-end ranking pipeline.

  JD  -> extract -> presence check (BLOCKS if fields missing)
  CVs -> extract -> match -> score -> rank
"""

from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .config import settings
from .embeddings import get_embedder
from .extract import extract_cv_safe, extract_jd
from .matching import match
from .schema import JobProfile
from .scoring import CandidateScore, rank, score_candidate

log = logging.getLogger(__name__)


class MissingRequirementsError(RuntimeError):
    """Raised when the JD lacks a mandatory field and no manual value was given.

    This mirrors the frontend rule, enforced server-side so it cannot be
    bypassed by calling the API directly.
    """

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(
            "Cannot rank: these requirements were not found in the job description "
            f"and were not supplied manually: {', '.join(missing)}"
        )


@dataclass
class FileFailure:
    path: str
    reason: str


@dataclass
class RankingRun:
    job: JobProfile
    scores: list[CandidateScore] = field(default_factory=list)
    failures: list[FileFailure] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    versions: dict[str, Any] = field(default_factory=dict)

    def top(self, n: int | None = None) -> list[CandidateScore]:
        return rank(self.scores, n)

    def to_dict(self, top_n: int | None = None) -> dict[str, Any]:
        return {
            "job_title": self.job.job_title,
            "requirements": {
                k: self.job.effective(k) for k in ("qualification", "experience", "age")
            },
            "required_skills": self.job.required_skills,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "versions": self.versions,
            "candidate_count": len(self.scores),
            "failures": [{"path": f.path, "reason": f.reason} for f in self.failures],
            "ranking": [s.to_dict() for s in self.top(top_n)],
        }

    def save(self, path: str | Path, top_n: int | None = None) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(top_n), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def prepare_job(jd_path: str | None = None, jd_text: str | None = None,
                manual_overrides: dict[str, Any] | None = None,
                required_skills: list[str] | None = None) -> JobProfile:
    """Extract the JD and apply any manual overrides.

    Manual values always take priority over what was found in the JD — the
    priority rule from the product specification.
    """
    job = extract_jd(path=jd_path, text=jd_text)
    if manual_overrides:
        job.manual_overrides = {k: v for k, v in manual_overrides.items() if v}
    if required_skills:
        job.required_skills = required_skills
    return job


def run_ranking(job: JobProfile, cv_paths: list[str], *,
                use_llm_transferability: bool = True,
                max_workers: int | None = None,
                progress: Optional[Callable[[int, int, str], None]] = None) -> RankingRun:
    """Score a batch of CVs against a prepared job profile."""
    missing = job.missing_requirements()
    if missing:
        raise MissingRequirementsError(missing)

    if max_workers is None:
        max_workers = settings.ranking_workers
    max_workers = max(1, min(max_workers, len(cv_paths) or 1))

    embedder = get_embedder()
    if not embedder.is_real:
        log.warning(
            "Running with a non-semantic embedding backend — results are structural only."
        )

    run = RankingRun(
        job=job,
        started_at=dt.datetime.now().isoformat(timespec="seconds"),
        versions={
            "scoring_engine": settings.scoring_engine_version,
            "embedding_model": embedder.name,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "schema": "1.0",
        },
    )

    total = len(cv_paths)

    def process_one(path: str) -> tuple[str, CandidateScore | None, str | None]:
        """Extract, match and score one CV.

        Extraction and matching are both network-bound: extraction is one LLM
        call, and matching spends up to MAX_TRANSFERABILITY_CALLS more asking
        whether a differently-named skill transfers. Keeping them in a single
        per-candidate task means a candidate's slow transferability questions
        overlap with another candidate's extraction, instead of the whole batch
        waiting at a barrier between two phases. On a real batch that is the
        difference between minutes and seconds.

        Never raises: one unreadable CV must not fail a batch of a hundred.
        """
        profile, err = extract_cv_safe(path)
        if profile is None:
            return path, None, err or "unknown error"
        try:
            m = match(profile, job, use_llm_transferability=use_llm_transferability)
            return path, score_candidate(profile, job, m, embedding_model=embedder.name), None
        except Exception as e:  # noqa: BLE001
            log.warning("Scoring failed for %s: %s", path, e)
            return path, None, str(e)

    results: list[tuple[str, CandidateScore | None, str | None]] = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(process_one, p) for p in cv_paths]
        for i, fut in enumerate(cf.as_completed(futures), 1):
            results.append(fut.result())
            if progress:
                progress(i, total, results[-1][0])

    # Completion order depends on thread timing, so sort back into a stable
    # order before scoring is recorded. Without this, two identical runs could
    # break ties differently and the same batch would rank differently twice.
    results.sort(key=lambda r: r[0])
    for path, score, err in results:
        if score is None:
            run.failures.append(FileFailure(path, err or "unknown error"))
        else:
            run.scores.append(score)

    run.finished_at = dt.datetime.now().isoformat(timespec="seconds")
    return run


def collect_cv_paths(folder: str | Path) -> list[str]:
    from .documents import SUPPORTED

    root = Path(folder)
    return sorted(
        str(p) for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )
