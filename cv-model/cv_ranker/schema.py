"""
Structured output contract for the extraction layer.

This schema is the interface between the LLM (which understands messy,
free-form CVs) and the scoring engine (which needs predictable fields).
Every downstream component depends on this shape, so changes here are
breaking changes — version it when you change it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Bumped whenever the schema changes shape. Stored with every extraction so
# old records stay interpretable.
SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# JSON Schema handed to the LLM to force structured output.
# Keep descriptions rich — they are effectively part of the prompt and do a
# lot of work in getting consistent extraction.
# ---------------------------------------------------------------------------

CV_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["candidate", "qualifications", "experience", "skills"],
    "additionalProperties": False,
    "properties": {
        "candidate": {
            "type": "object",
            "required": ["name"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "description": "Full name as written on the CV."},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "age": {
                    "type": ["integer", "null"],
                    "description": (
                        "Age in years ONLY if stated or directly computable from a stated "
                        "date of birth. Never estimate age from graduation year or work history."
                    ),
                },
                "date_of_birth": {"type": ["string", "null"], "description": "ISO date if stated."},
            },
        },
        "qualifications": {
            "type": "array",
            "description": "Every distinct educational qualification, most recent first.",
            "items": {
                "type": "object",
                "required": ["degree_title", "level", "field_of_study"],
                "additionalProperties": False,
                "properties": {
                    "degree_title": {
                        "type": "string",
                        "description": "Exactly as written on the CV, e.g. 'BSc Mechanical Engineering'.",
                    },
                    "level": {
                        "type": "string",
                        "enum": [
                            "matric",
                            "intermediate",
                            "diploma",
                            "bachelors",
                            "masters",
                            "mphil",
                            "phd",
                            "certification",
                            "unknown",
                        ],
                        "description": (
                            "Normalised academic level. Map local qualifications sensibly: "
                            "BS/BSc/BE/BTech/BBA -> bachelors; MS/MSc/ME/MTech/MBA -> masters; "
                            "FSc/FA/A-Levels -> intermediate; Matric/O-Levels -> matric."
                        ),
                    },
                    "field_of_study": {
                        "type": "string",
                        "description": "e.g. 'Mechanical Engineering'. Use the CV's own wording.",
                    },
                    "institution": {"type": ["string", "null"]},
                    "completion_year": {"type": ["integer", "null"]},
                    "is_completed": {
                        "type": "boolean",
                        "description": "False if in progress / expected.",
                    },
                },
            },
        },
        "experience": {
            "type": "array",
            "description": (
                "Every work entry including internships, part-time and freelance work. "
                "Do not merge separate roles at the same employer."
            ),
            "items": {
                "type": "object",
                "required": ["job_title", "employment_type", "description", "duration_years"],
                "additionalProperties": False,
                "properties": {
                    "job_title": {"type": "string"},
                    "employer": {"type": ["string", "null"]},
                    "employment_type": {
                        "type": "string",
                        "enum": [
                            "full_time",
                            "part_time",
                            "internship",
                            "contract",
                            "freelance",
                            "unknown",
                        ],
                    },
                    "start_date": {"type": ["string", "null"], "description": "YYYY-MM if known."},
                    "end_date": {
                        "type": ["string", "null"],
                        "description": "YYYY-MM, or null if current role.",
                    },
                    "is_current": {"type": "boolean"},
                    "duration_years": {
                        "type": "number",
                        "description": (
                            "Duration in years as a decimal, computed from the dates. "
                            "If dates are vague, give your best estimate from what is stated."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "What the person actually did — responsibilities, tools, domain. "
                            "This text is embedded and compared against the job description, "
                            "so preserve technical specifics rather than summarising them away."
                        ),
                    },
                    "technologies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools, software, frameworks or techniques named in this role.",
                    },
                },
            },
        },
        "skills": {
            "type": "array",
            "description": (
                "Every distinct skill, tool, framework or competency, written as it appears "
                "on the CV. Do NOT normalise or rename them — the matching layer handles "
                "synonyms semantically. Include skills implied by role descriptions."
            ),
            "items": {"type": "string"},
        },
        "certifications": {"type": "array", "items": {"type": "string"}},
        "languages": {"type": "array", "items": {"type": "string"}},
        "extraction_notes": {
            "type": ["string", "null"],
            "description": (
                "Anything ambiguous, contradictory or unreadable in the CV that a human "
                "reviewer should know about. Null if the CV was clean."
            ),
        },
    },
}


JD_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["job_title", "required_skills", "requirements"],
    "additionalProperties": False,
    "properties": {
        "job_title": {"type": "string"},
        "summary": {"type": ["string", "null"], "description": "One-sentence role summary."},
        "responsibilities_text": {
            "type": ["string", "null"],
            "description": (
                "The duties/responsibilities section as continuous text. Embedded and compared "
                "against candidate experience, so keep it verbatim rather than summarised."
            ),
        },
        "required_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills stated as required or essential, in the JD's own wording.",
        },
        "preferred_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills stated as desirable / nice-to-have / preferred.",
        },
        "requirements": {
            "type": "object",
            "required": ["qualification", "experience", "age"],
            "additionalProperties": False,
            "description": (
                "The three mandatory presence-checked fields. For each, report whether the JD "
                "mentions it at all, and if so quote the exact sentence. Presence, not "
                "interpretation, is what matters — do not infer a requirement that is not stated."
            ),
            "properties": {
                "qualification": {"$ref": "#/$defs/requirement_field"},
                "experience": {"$ref": "#/$defs/requirement_field"},
                "age": {"$ref": "#/$defs/requirement_field"},
            },
        },
    },
    "$defs": {
        "requirement_field": {
            "type": "object",
            "required": ["mentioned"],
            "additionalProperties": False,
            "properties": {
                "mentioned": {
                    "type": "boolean",
                    "description": "True only if the JD text actually states this requirement.",
                },
                "quoted_text": {
                    "type": ["string", "null"],
                    "description": "The exact sentence from the JD, verbatim. Null if not mentioned.",
                },
                "min_value": {
                    "type": ["number", "null"],
                    "description": "Lower bound if numeric (years / age). Null otherwise.",
                },
                "max_value": {"type": ["number", "null"]},
                "level": {
                    "type": ["string", "null"],
                    "description": "For qualification only: the normalised level enum, e.g. 'bachelors'.",
                },
                "field_of_study": {
                    "type": ["string", "null"],
                    "description": "For qualification only, e.g. 'Mechanical Engineering'.",
                },
            },
        }
    },
}


# ---------------------------------------------------------------------------
# Lightweight dataclasses — convenience wrappers over the extracted dicts.
# Deliberately tolerant: a missing optional field must never crash a batch.
# ---------------------------------------------------------------------------


@dataclass
class Qualification:
    degree_title: str
    level: str
    field_of_study: str
    institution: Optional[str] = None
    completion_year: Optional[int] = None
    is_completed: bool = True


@dataclass
class ExperienceEntry:
    job_title: str
    employment_type: str
    description: str
    duration_years: float
    employer: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    technologies: list[str] = field(default_factory=list)


@dataclass
class CandidateProfile:
    """The versioned, structured record that the scoring engine consumes."""

    name: str
    qualifications: list[Qualification]
    experience: list[ExperienceEntry]
    skills: list[str]
    email: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    extraction_notes: Optional[str] = None
    source_file: Optional[str] = None
    schema_version: str = SCHEMA_VERSION
    extraction_model: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any], source_file: str | None = None,
                  extraction_model: str | None = None) -> "CandidateProfile":
        cand = d.get("candidate", {}) or {}
        return cls(
            name=cand.get("name") or "Unknown",
            email=cand.get("email"),
            phone=cand.get("phone"),
            age=cand.get("age"),
            qualifications=[
                Qualification(
                    degree_title=q.get("degree_title", ""),
                    level=q.get("level", "unknown"),
                    field_of_study=q.get("field_of_study", ""),
                    institution=q.get("institution"),
                    completion_year=q.get("completion_year"),
                    is_completed=q.get("is_completed", True),
                )
                for q in d.get("qualifications", []) or []
            ],
            experience=[
                ExperienceEntry(
                    job_title=e.get("job_title", ""),
                    employer=e.get("employer"),
                    employment_type=e.get("employment_type", "unknown"),
                    start_date=e.get("start_date"),
                    end_date=e.get("end_date"),
                    is_current=e.get("is_current", False),
                    duration_years=float(e.get("duration_years") or 0.0),
                    description=e.get("description", ""),
                    technologies=e.get("technologies", []) or [],
                )
                for e in d.get("experience", []) or []
            ],
            skills=d.get("skills", []) or [],
            certifications=d.get("certifications", []) or [],
            languages=d.get("languages", []) or [],
            extraction_notes=d.get("extraction_notes"),
            source_file=source_file,
            extraction_model=extraction_model,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobProfile:
    job_title: str
    required_skills: list[str]
    requirements: dict[str, Any]
    preferred_skills: list[str] = field(default_factory=list)
    responsibilities_text: Optional[str] = None
    summary: Optional[str] = None
    source_file: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    # Manually entered overrides. Per the product spec, a manual value ALWAYS
    # takes priority over anything detected in the JD.
    manual_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any], source_file: str | None = None) -> "JobProfile":
        return cls(
            job_title=d.get("job_title", ""),
            summary=d.get("summary"),
            responsibilities_text=d.get("responsibilities_text"),
            required_skills=d.get("required_skills", []) or [],
            preferred_skills=d.get("preferred_skills", []) or [],
            requirements=d.get("requirements", {}) or {},
            source_file=source_file,
        )

    def _override_value(self, key: str) -> str:
        """Meaningful content of a manual override, or "" if there is none.

        Careful here: a dict like {"text": "   "} is truthy, so a naive
        truthiness check would let a blank value unblock a mandatory field.
        """
        ov = self.manual_overrides.get(key)
        if ov is None:
            return ""
        if isinstance(ov, dict):
            parts = [
                ov.get("text"),
                ov.get("min_value"),
                ov.get("max_value"),
                ov.get("level"),
                ov.get("field_of_study"),
            ]
            return " ".join(str(p).strip() for p in parts if p is not None and str(p).strip())
        return str(ov).strip()

    def missing_requirements(self) -> list[str]:
        """Fields not present in the JD and not supplied manually.

        Ranking must be blocked while this is non-empty — that is the
        product rule from the spec, enforced here in the backend so the
        frontend check can't be bypassed.
        """
        missing = []
        for key in ("qualification", "experience", "age"):
            mentioned = (self.requirements.get(key) or {}).get("mentioned", False)
            overridden = bool(self._override_value(key))
            if not mentioned and not overridden:
                missing.append(key)
        return missing

    def effective(self, key: str) -> dict[str, Any]:
        """Resolved value for a requirement, applying the manual-override rule."""
        jd_value = dict(self.requirements.get(key) or {})
        override = self.manual_overrides.get(key)
        if self._override_value(key):
            return {
                "source": "manual",
                "text": override.get("text") if isinstance(override, dict) else str(override),
                "min_value": (override or {}).get("min_value") if isinstance(override, dict) else None,
                "max_value": (override or {}).get("max_value") if isinstance(override, dict) else None,
                "level": (override or {}).get("level") if isinstance(override, dict) else None,
                "field_of_study": (override or {}).get("field_of_study") if isinstance(override, dict) else None,
            }
        return {
            "source": "job_description",
            "text": jd_value.get("quoted_text"),
            "min_value": jd_value.get("min_value"),
            "max_value": jd_value.get("max_value"),
            "level": jd_value.get("level"),
            "field_of_study": jd_value.get("field_of_study"),
        }
