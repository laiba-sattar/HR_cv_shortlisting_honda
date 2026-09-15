"""CV ranking model pipeline for the HR CV Shortlisting System."""

from .config import settings
from .schema import CandidateProfile, JobProfile
from .pipeline import (
    MissingRequirementsError,
    RankingRun,
    collect_cv_paths,
    prepare_job,
    run_ranking,
)

__version__ = "0.1.0"

__all__ = [
    "settings",
    "CandidateProfile",
    "JobProfile",
    "RankingRun",
    "MissingRequirementsError",
    "prepare_job",
    "run_ranking",
    "collect_cv_paths",
]
