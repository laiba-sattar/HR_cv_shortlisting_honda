"""
Unit tests for the deterministic parts of the pipeline.

These deliberately avoid the model: they test the rules that must hold
regardless of which LLM or embedding model is configured — the priority rule,
the blocking rule, the weighting, determinism, and edge cases.
"""

from __future__ import annotations

import pytest

from cv_ranker.config import settings
from cv_ranker.matching import ExperienceRelevance, MatchResult, SkillMatch
from cv_ranker.schema import (
    CandidateProfile,
    ExperienceEntry,
    JobProfile,
    Qualification,
)
from cv_ranker.scoring import LEVEL_RANK, rank, score_candidate, score_experience


def make_job(**kw) -> JobProfile:
    reqs = {
        "qualification": {"mentioned": True, "quoted_text": "Bachelor's in Mechanical Engineering",
                          "level": "bachelors", "field_of_study": "Mechanical Engineering",
                          "min_value": None, "max_value": None},
        "experience": {"mentioned": True, "quoted_text": "2-4 years relevant experience",
                       "min_value": 2, "max_value": 4, "level": None, "field_of_study": None},
        "age": {"mentioned": True, "quoted_text": "22-30 years",
                "min_value": 22, "max_value": 30, "level": None, "field_of_study": None},
    }
    reqs.update(kw.pop("requirements", {}))
    return JobProfile(
        job_title=kw.pop("job_title", "Mechanical Design Engineer"),
        required_skills=kw.pop("required_skills", ["AutoCAD", "SolidWorks"]),
        requirements=reqs,
        **kw,
    )


def make_candidate(**kw) -> CandidateProfile:
    return CandidateProfile(
        name=kw.pop("name", "Test Candidate"),
        qualifications=kw.pop("qualifications", [
            Qualification("BSc Mechanical Engineering", "bachelors", "Mechanical Engineering")
        ]),
        experience=kw.pop("experience", [
            ExperienceEntry("Design Engineer", "full_time", "CAD design work", 3.0)
        ]),
        skills=kw.pop("skills", ["AutoCAD", "SolidWorks"]),
        **kw,
    )


# ---------------------------------------------------------------------------
# The product rules that must never break
# ---------------------------------------------------------------------------


class TestPriorityRule:
    """A manually entered value ALWAYS overrides the job description."""

    def test_manual_overrides_jd(self):
        job = make_job()
        assert job.effective("experience")["source"] == "job_description"
        assert job.effective("experience")["min_value"] == 2

        job.manual_overrides = {"experience": {"text": "5+ years", "min_value": 5}}
        eff = job.effective("experience")
        assert eff["source"] == "manual"
        assert eff["min_value"] == 5

    def test_manual_fills_a_field_absent_from_jd(self):
        job = make_job(requirements={"age": {"mentioned": False, "quoted_text": None,
                                             "min_value": None, "max_value": None,
                                             "level": None, "field_of_study": None}})
        assert "age" in job.missing_requirements()
        job.manual_overrides = {"age": {"text": "22-30", "min_value": 22, "max_value": 30}}
        assert "age" not in job.missing_requirements()
        assert job.effective("age")["source"] == "manual"


class TestBlockingRule:
    """Ranking must be blocked while a mandatory field is unresolved."""

    def test_all_present_is_not_blocked(self):
        assert make_job().missing_requirements() == []

    def test_each_missing_field_blocks(self):
        for key in ("qualification", "experience", "age"):
            job = make_job(requirements={key: {"mentioned": False, "quoted_text": None,
                                               "min_value": None, "max_value": None,
                                               "level": None, "field_of_study": None}})
            assert job.missing_requirements() == [key]

    def test_pipeline_raises_when_blocked(self):
        from cv_ranker.pipeline import MissingRequirementsError, run_ranking

        job = make_job(requirements={"age": {"mentioned": False, "quoted_text": None,
                                             "min_value": None, "max_value": None,
                                             "level": None, "field_of_study": None}})
        with pytest.raises(MissingRequirementsError) as exc:
            run_ranking(job, ["dummy.pdf"])
        assert "age" in exc.value.missing

    def test_blank_manual_value_does_not_unblock(self):
        job = make_job(requirements={"age": {"mentioned": False, "quoted_text": None,
                                             "min_value": None, "max_value": None,
                                             "level": None, "field_of_study": None}})
        job.manual_overrides = {"age": {"text": "   "}}
        assert "age" in job.missing_requirements()


class TestWeighting:
    """33/33/33 is fixed by the specification."""

    def test_weights_sum_to_one(self):
        assert settings.weights_sum_to_one

    def test_final_is_equal_weighted_mean(self):
        m = MatchResult(
            skill_matches=[SkillMatch("AutoCAD", "AutoCAD", 1.0, 1.0, "direct")],
            experience_relevance=[],
            relevant_years=3.0,
            jd_similarity=0.8,
        )
        score = score_candidate(make_candidate(), make_job(), m, embedding_model="test")
        expected = (score.qualification.value + score.experience.value + score.jd_skills.value) / 3
        assert score.final == pytest.approx(expected, abs=0.1)


class TestDeterminism:
    """The same inputs must always produce the same score and ordering."""

    def test_repeated_scoring_is_identical(self):
        cand, job = make_candidate(), make_job()
        m = MatchResult(relevant_years=3.0, jd_similarity=0.8)
        a = score_candidate(cand, job, m, embedding_model="t")
        b = score_candidate(cand, job, m, embedding_model="t")
        assert a.final == b.final
        assert a.experience.value == b.experience.value

    def test_ties_break_deterministically(self):
        m = MatchResult(relevant_years=3.0, jd_similarity=0.8)
        job = make_job()
        scores = [
            score_candidate(make_candidate(name=n), job, m, embedding_model="t")
            for n in ["Zara", "Ahmed", "Maria"]
        ]
        for s in scores:
            s.final = 75.0
        assert [s.candidate_name for s in rank(scores)] == ["Ahmed", "Maria", "Zara"]


# ---------------------------------------------------------------------------
# Scoring behaviour
# ---------------------------------------------------------------------------


class TestExperienceScoring:
    """Relevant experience, not total years."""

    def test_relevant_beats_total(self):
        job = make_job()
        cand = make_candidate(experience=[
            ExperienceEntry("Chef", "full_time", "kitchen work", 10.0),
        ])
        low = score_experience(cand, job, MatchResult(relevant_years=0.2))
        high = score_experience(cand, job, MatchResult(relevant_years=3.0))
        assert high.value > low.value
        assert high.value == 100.0  # 3 relevant years meets a 2-year requirement

    def test_meeting_requirement_is_full_marks(self):
        s = score_experience(make_candidate(), make_job(), MatchResult(relevant_years=2.0))
        assert s.value == 100.0

    def test_partial_experience_scores_proportionally(self):
        s = score_experience(make_candidate(), make_job(), MatchResult(relevant_years=1.0))
        assert s.value == pytest.approx(50.0, abs=1.0)

    def test_fresh_graduate_role_accepts_zero_experience(self):
        job = make_job(requirements={"experience": {
            "mentioned": True, "quoted_text": "Fresh graduates welcome",
            "min_value": 0, "max_value": None, "level": None, "field_of_study": None}})
        s = score_experience(make_candidate(), job, MatchResult(relevant_years=0.0))
        assert s.value == 100.0

    def test_no_numeric_requirement_does_not_crash_or_zero(self):
        job = make_job(requirements={"experience": {
            "mentioned": True, "quoted_text": "Relevant industry experience",
            "min_value": None, "max_value": None, "level": None, "field_of_study": None}})
        s = score_experience(make_candidate(), job, MatchResult(relevant_years=2.0))
        assert 0 < s.value <= 100


class TestQualificationLevels:
    def test_level_ordering_is_ordinal(self):
        assert LEVEL_RANK["phd"] > LEVEL_RANK["masters"] > LEVEL_RANK["bachelors"]
        assert LEVEL_RANK["bachelors"] > LEVEL_RANK["intermediate"] > LEVEL_RANK["matric"]


class TestAgeHandling:
    """Age must be reported for human judgement, never folded into the score."""

    def test_out_of_range_age_flags_but_does_not_change_score(self):
        job, m = make_job(), MatchResult(relevant_years=3.0, jd_similarity=0.8)
        in_range = score_candidate(make_candidate(age=25), job, m, embedding_model="t")
        out_range = score_candidate(make_candidate(age=45), job, m, embedding_model="t")
        assert in_range.final == out_range.final
        assert not in_range.flags
        assert any("Age 45" in f for f in out_range.flags)


class TestRobustness:
    """One bad record must never break a batch of 100."""

    def test_empty_candidate_scores_zero_not_crash(self):
        cand = CandidateProfile(name="Empty", qualifications=[], experience=[], skills=[])
        s = score_candidate(cand, make_job(), MatchResult(), embedding_model="t")
        assert s.final >= 0
        assert len(s.flags) >= 2

    def test_scores_stay_within_bounds(self):
        job = make_job()
        m = MatchResult(
            skill_matches=[SkillMatch("AutoCAD", "AutoCAD", 1.0, 1.0, "direct")],
            relevant_years=99.0,
            jd_similarity=1.0,
        )
        cand = make_candidate(qualifications=[
            Qualification("PhD Mechanical Engineering", "phd", "Mechanical Engineering")
        ])
        s = score_candidate(cand, job, m, embedding_model="t")
        for v in (s.qualification.value, s.experience.value, s.jd_skills.value, s.final):
            assert 0.0 <= v <= 100.0

    def test_top_n_selection(self):
        job, m = make_job(), MatchResult(relevant_years=3.0)
        scores = []
        for i in range(30):
            s = score_candidate(make_candidate(name=f"C{i:02d}"), job, m, embedding_model="t")
            s.final = float(i)
            scores.append(s)
        for n in (5, 10, 20, 30):
            assert len(rank(scores, n)) == n
        assert rank(scores, 5)[0].final == 29.0


class TestTransferability:
    """Partial credit for a different-but-transferable skill."""

    def test_partial_credit_lands_between_match_and_miss(self):
        job = make_job(required_skills=["React"])
        cand, base = make_candidate(), MatchResult(relevant_years=3.0, jd_similarity=0.5)

        def skills_score(credit, method):
            m = MatchResult(
                skill_matches=[SkillMatch("React", "Vue.js", 0.55, credit, method)],
                relevant_years=base.relevant_years,
                jd_similarity=base.jd_similarity,
            )
            return score_candidate(cand, job, m, embedding_model="t").jd_skills.value

        assert skills_score(0.0, "none") < skills_score(0.7, "transferable") < skills_score(1.0, "direct")


class TestScoringGuards:
    """Regressions for two flaws found by running the sample batch."""

    def test_long_unrelated_career_does_not_accumulate_relevant_years(self):
        """An accountant must not score highly on an engineering role's
        experience requirement just because the career was long."""
        from cv_ranker.config import settings
        from cv_ranker.matching import score_experience_relevance

        job = make_job()
        accountant = make_candidate(
            name="Accountant",
            experience=[ExperienceEntry("Senior Accountant", "full_time",
                                        "Accounts payable and receivable, audit support", 7.0)],
        )
        roles, total = score_experience_relevance(accountant, job)
        # Whatever the embedder says, anything under the floor must contribute 0.
        for r in roles:
            if r.relevance < settings.experience_relevance_floor:
                assert r.weighted_years == 0.0
        assert total == sum(r.weighted_years for r in roles)

    def test_right_level_wrong_field_scores_low(self):
        """A bachelor's in an unrelated field must not inherit a high score
        from meeting the level alone."""
        from cv_ranker.scoring import score_qualification

        job = make_job()  # requires bachelors in Mechanical Engineering
        finance = make_candidate(qualifications=[
            Qualification("BBA (Hons) Finance", "bachelors", "Finance")
        ])
        mech = make_candidate(qualifications=[
            Qualification("BSc Mechanical Engineering", "bachelors", "Mechanical Engineering")
        ])
        assert score_qualification(finance, job).value < score_qualification(mech, job).value

    def test_no_required_field_does_not_penalise(self):
        from cv_ranker.scoring import score_qualification

        job = make_job(requirements={"qualification": {
            "mentioned": True, "quoted_text": "Bachelor's degree",
            "level": "bachelors", "field_of_study": None,
            "min_value": None, "max_value": None}})
        assert score_qualification(make_candidate(), job).value == 100.0


# --- contact details reach the result --------------------------------------
#
# The extractor reads an email out of the CV and the scorer used to drop it, so
# a shortlist named people it gave the reviewer no way to contact. These assert
# the value travels, and that it stays out of the arithmetic.


def _profile_with_contact(**over):
    from cv_ranker.schema import CandidateProfile
    d = dict(name="Ayesha Raza", email="ayesha.raza@example.com", phone="+923001234567")
    d.update(over)
    return CandidateProfile(**d)


def test_email_and_phone_survive_into_the_scored_result():
    from cv_ranker.scoring import CandidateScore, SubScore

    s = CandidateScore(
        candidate_name="Ayesha Raza",
        email="ayesha.raza@example.com",
        phone="+923001234567",
        qualification=SubScore(80.0, "", {}),
        experience=SubScore(70.0, "", {}),
        jd_skills=SubScore(60.0, "", {}),
        final=70.0,
    )
    d = s.to_dict()
    assert d["email"] == "ayesha.raza@example.com"
    assert d["phone"] == "+923001234567"


def test_a_missing_email_is_null_rather_than_an_empty_string():
    """A CV with no address must say so, not look like an empty inbox."""
    from cv_ranker.scoring import CandidateScore, SubScore

    d = CandidateScore(
        candidate_name="No Contact",
        qualification=SubScore(80.0, "", {}),
        experience=SubScore(70.0, "", {}),
        jd_skills=SubScore(60.0, "", {}),
        final=70.0,
    ).to_dict()
    assert d["email"] is None
    assert d["phone"] is None


def test_contact_details_do_not_change_any_score():
    """Two identical candidates, one with contact details, must score the same."""
    from cv_ranker.scoring import CandidateScore, SubScore

    def build(**contact):
        return CandidateScore(
            candidate_name="Same Person",
            qualification=SubScore(80.0, "", {}),
            experience=SubScore(70.0, "", {}),
            jd_skills=SubScore(60.0, "", {}),
            final=70.0,
            **contact,
        ).to_dict()

    with_contact = build(email="a@b.com", phone="+920000000000")
    without = build()
    assert with_contact["final_score"] == without["final_score"]
    assert with_contact["scores"] == without["scores"]
