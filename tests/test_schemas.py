"""tests/test_schemas.py – Unit-Tests für Pydantic-Schemas."""

import pytest
from datetime import datetime
from src.agent.schemas import (
    AgentState,
    ApplicationStatus,
    AuditLogEntry,
    CVVariant,
    ErrorLogEntry,
    EvaluateRequest,
    EvaluateResponse,
    JobListing,
    JobSource,
    ProfileSummary,
    RejectedJob,
    StoredJob,
    WeeklyKPI,
    WorkMode,
)


# ── JobListing Tests ──────────────────────────────────────────────

class TestJobListing:
    def test_basic_creation(self):
        job = JobListing(
            id="abc123",
            title="Senior UX Designer",
            company="TestCorp",
            url="https://example.com/job",
            source=JobSource.LINKEDIN,
            description="Great job opportunity with many benefits...",
        )
        assert job.title == "Senior UX Designer"
        assert job.source == JobSource.LINKEDIN
        assert job.has_email_contact is True

    def test_with_all_fields(self):
        job = JobListing(
            id="def456",
            title="Product Owner",
            company="Awesome GmbH",
            location="Berlin",
            url="https://stepstone.de/job/123",
            source=JobSource.STEPSTONE,
            description="We are looking for a Product Owner with 5 years experience...",
            requirements=["Scrum", "Jira", "Agile"],
            salary_range="60k-80k",
            remote_type=WorkMode.HYBRID,
            has_email_contact=False,
        )
        assert len(job.requirements) == 3
        assert job.remote_type == WorkMode.HYBRID
        assert job.has_email_contact is False

    def test_idempotency(self):
        """JobListing sollte frozen sein (immutable)."""
        job = JobListing(
            id="abc",
            title="Test Job Title",
            company="Co",
            url="https://example.com",
            source=JobSource.INDEED,
            description="This is a longer description that meets the minimum length requirement.",
        )
        with pytest.raises((AttributeError, Exception)):
            job.title = "Changed"


# ── EvaluateResponse Tests ────────────────────────────────────────

class TestEvaluateResponse:
    def test_valid_response(self):
        response = EvaluateResponse(
            score=8.5,
            reasoning="Strong match with multiple skills aligned.",
            adapted_cover_letter="Hello, I am the local automation agent of Daniel Peters. "
                                 "I have analyzed this position and determined it is a strong match.",
            matched_keywords=["Figma", "UX", "Agile"],
            missing_keywords=["React"],
            profile_tip="Consider adding React to your skill set.",
            selected_cv_variant="product_owner",
            agent_voice_confidence=0.85,
        )
        assert response.score == 8.5
        assert response.profile_tip is not None
        assert response.selected_cv_variant == "product_owner"

    def test_minimal_response(self):
        response = EvaluateResponse(
            score=5.0,
            reasoning="Basic match.",
            adapted_cover_letter="Hello, I am the agent. This role fits your profile moderately well.",
        )
        assert response.agent_voice_confidence == 0.0  # default
        assert response.profile_tip is None

    def test_score_out_of_range_high(self):
        with pytest.raises(ValueError):
            EvaluateResponse(
                score=15,
                reasoning="test",
                adapted_cover_letter="Hello, I am the agent. " * 10,
            )

    def test_score_out_of_range_low(self):
        with pytest.raises(ValueError):
            EvaluateResponse(
                score=-1,
                reasoning="test",
                adapted_cover_letter="Hello, I am the agent. " * 10,
            )

    def test_short_cover_letter_rejected(self):
        with pytest.raises(ValueError):
            EvaluateResponse(
                score=7.0,
                reasoning="test",
                adapted_cover_letter="Too short.",
            )


# ── ProfileSummary Tests ──────────────────────────────────────────

class TestProfileSummary:
    def test_defaults(self):
        profile = ProfileSummary(
            name="Daniel Peters",
            title="UX Designer",
            skills=["Figma"],
            experience_years=5,
        )
        assert profile.portfolio_url == "portfolio.untitled-ux.de"
        assert profile.photo_included is True
        assert profile.salary_min == 56000

    def test_with_linkedin(self):
        profile = ProfileSummary(
            name="Test",
            title="Dev",
            skills=["Python"],
            experience_years=3,
            linkedin_url="https://linkedin.com/in/test",
        )
        assert profile.linkedin_url is not None


# ── EvaluateRequest Tests ─────────────────────────────────────────

class TestEvaluateRequest:
    def test_basic_request(self):
        job = JobListing(
            id="123",
            title="UX Lead",
            company="Corp",
            url="https://corp.de/job",
            source=JobSource.LINKEDIN,
            description="Leading the UX team...",
        )
        profile = ProfileSummary(
            name="Daniel",
            title="UX",
            skills=["Figma"],
            experience_years=5,
        )
        request = EvaluateRequest(
            job=job,
            profile=profile,
            cv_variants=["general.tex", "product.tex"],
            voice_samples=["Sample text..."],
        )
        assert request.application_language == "de"  # default
        assert len(request.cv_variants) == 2

    def test_rejected_context_limit(self):
        """Max 5 rejected jobs in context."""
        now = datetime.utcnow()
        rejected = [
            RejectedJob(
                job_title=f"Job {i}",
                company="Corp",
                rejection_reason="Not a good fit for my career goals.",
                score=3.0,
                rejected_at=now,
            )
            for i in range(10)
        ]
        job = JobListing(
            id="123", title="Test", company="Co",
            url="https://example.com", source=JobSource.INDEED,
            description="This is a description with enough characters.",
        )
        profile = ProfileSummary(name="T", title="D", skills=["S"], experience_years=1)
        request = EvaluateRequest(
            job=job, profile=profile, rejected_context=rejected[:5]
        )
        assert len(request.rejected_context) <= 5


# ── AgentState Tests ──────────────────────────────────────────────

class TestAgentState:
    def test_defaults(self):
        state = AgentState()
        assert state.paused is False
        assert state.quiet_mode is False
        assert state.total_api_calls_this_month == 0

    def test_with_values(self):
        state = AgentState(
            paused=True,
            quiet_mode=True,
            total_api_calls_this_month=150,
            api_budget_reached=True,
        )
        assert state.paused is True
        assert state.api_budget_reached is True


# ── WeeklyKPI Tests ───────────────────────────────────────────────

class TestWeeklyKPI:
    def test_basic_kpi(self):
        kpi = WeeklyKPI(
            week_start=datetime(2024, 1, 1),
            week_end=datetime(2024, 1, 7),
            jobs_scanned=50,
            proposals_sent=10,
            rejects=3,
            accepted=1,
            avg_score=7.5,
        )
        assert kpi.jobs_scanned == 50
        assert kpi.avg_score == 7.5

    def test_zero_values(self):
        kpi = WeeklyKPI(
            week_start=datetime(2024, 1, 1),
            week_end=datetime(2024, 1, 7),
            jobs_scanned=0,
            proposals_sent=0,
            rejects=0,
            accepted=0,
            avg_score=0.0,
        )
        assert kpi.jobs_scanned == 0


# ── Enum Tests ────────────────────────────────────────────────────

class TestEnums:
    def test_job_source_values(self):
        assert JobSource.LINKEDIN.value == "linkedin"
        assert JobSource.STEPSTONE.value == "stepstone"
        assert JobSource.INDEED.value == "indeed"

    def test_application_status_values(self):
        assert ApplicationStatus.PENDING.value == "pending"
        assert ApplicationStatus.SENT.value == "sent"
        assert ApplicationStatus.REJECTED.value == "rejected"

    def test_work_mode_values(self):
        assert WorkMode.REMOTE.value == "remote"
        assert WorkMode.HYBRID.value == "hybrid"
        assert WorkMode.ONSITE.value == "onsite"


# ── CVVariant Tests ───────────────────────────────────────────────

class TestCVVariant:
    def test_creation(self):
        cv = CVVariant(
            name="Product Owner",
            file_path="/data/cv/product_owner.tex",
            description="Focus on product leadership",
            suitable_for=["Product Owner", "Product Manager"],
        )
        assert cv.name == "Product Owner"
        assert len(cv.suitable_for) == 2
