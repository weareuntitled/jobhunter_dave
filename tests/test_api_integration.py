"""tests/test_api_integration.py – Integrationstest: GoAPIClient gegen Mock-Server."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.client import GoAPIClient
from src.agent.schemas import JobListing, JobSource, ProfileSummary, RejectedJob
from src.api.mock_server import create_app, state


@pytest.fixture
def app():
    state.evaluate_calls.clear()
    return create_app()


@pytest.fixture
async def api_client(app):
    """Erstellt einen echten GoAPIClient, der gegen den Mock-Server routed."""
    transport = ASGITransport(app=app)
    httpx_client = AsyncClient(transport=transport, base_url="http://test")

    client = GoAPIClient({
        "base_url": "http://test",
        "evaluate_endpoint": "/api/v1/evaluate",
        "timeout_seconds": 10,
    })
    # Override the internal httpx client with our ASGI-routed one
    client.client = httpx_client
    yield client
    await client.close()


@pytest.fixture
def sample_job():
    return JobListing(
        id="int-test-1",
        title="Senior UX Designer",
        company="TechCorp GmbH",
        location="Berlin (Hybrid)",
        url="https://techcorp.de/job/ux-designer",
        source=JobSource.LINKEDIN,
        description="Wir suchen einen erfahrenen UX Designer mit Figma, "
                    "Prototyping und User Research Skills für unser Produkt-Team.",
    )


@pytest.fixture
def sample_profile():
    return ProfileSummary(
        name="Daniel Peters",
        title="UX Designer",
        skills=["Figma", "UX Design", "Prototyping", "User Research"],
        experience_years=9,
    )


class TestGoAPIClientIntegration:
    @pytest.mark.asyncio
    async def test_evaluate_returns_valid_response(self, api_client, sample_job, sample_profile):
        result = await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex", "general.tex"],
            voice_samples=[],
            language="de",
        )

        assert 0 <= result.score <= 10
        assert len(result.reasoning) > 10
        assert len(result.adapted_cover_letter) > 50
        assert result.selected_cv_variant is not None

    @pytest.mark.asyncio
    async def test_evaluate_matches_skills(self, api_client, sample_job, sample_profile):
        result = await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
            language="de",
        )

        assert "figma" in result.matched_keywords
        assert "ux design" in result.matched_keywords

    @pytest.mark.asyncio
    async def test_evaluate_tracks_on_server(self, api_client, sample_job, sample_profile):
        await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
        )

        assert len(state.evaluate_calls) == 1
        server_body = state.evaluate_calls[0]
        assert server_body["job"]["title"] == "Senior UX Designer"

    @pytest.mark.asyncio
    async def test_evaluate_with_rejected_context(self, api_client, sample_job, sample_profile):
        from datetime import datetime

        rejected = [
            RejectedJob(
                job_title="Junior Designer",
                company="BadCorp",
                rejection_reason="Gehalt zu niedrig für meine Erfahrung.",
                score=3.0,
                rejected_at=datetime.utcnow(),
            )
        ]

        result = await api_client.evaluate(
            job=sample_job,
            rejected=rejected,
            profile=sample_profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
        )

        assert result.score >= 5.0  # Should not be affected negatively

    @pytest.mark.asyncio
    async def test_evaluate_german_cover_letter(self, api_client, sample_job, sample_profile):
        result = await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
            language="de",
        )

        assert "KI-Tools" in result.adapted_cover_letter

    @pytest.mark.asyncio
    async def test_evaluate_english_cover_letter(self, api_client, sample_job, sample_profile):
        result = await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
            language="en",
        )

        assert "AI" in result.adapted_cover_letter

    @pytest.mark.asyncio
    async def test_evaluate_cv_selection(self, api_client, sample_job, sample_profile):
        result = await api_client.evaluate(
            job=sample_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["ux.tex", "backend.tex", "general.tex"],
            voice_samples=[],
        )

        assert "ux" in result.selected_cv_variant.lower()

    @pytest.mark.asyncio
    async def test_evaluate_low_score_for_mismatch(self, api_client, sample_profile):
        mismatch_job = JobListing(
            id="mismatch-1",
            title="Nuclear Physicist",
            company="CERN",
            location="Geneva",
            url="https://cern.ch/job",
            source=JobSource.LINKEDIN,
            description="Quantum mechanics and particle physics expert needed.",
        )

        result = await api_client.evaluate(
            job=mismatch_job,
            rejected=[],
            profile=sample_profile,
            cv_variants=["general.tex"],
            voice_samples=[],
        )

        assert result.score < 7.0
        assert len(result.missing_keywords) > 0
