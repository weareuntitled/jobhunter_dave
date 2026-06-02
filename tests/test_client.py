"""tests/test_client.py – Tests für Go-API Client (inkl. Mock)."""

import pytest
from src.agent.client import GoAPIClient, MockGoAPIClient, create_api_client
from src.agent.schemas import JobListing, JobSource, ProfileSummary


class TestMockGoAPIClient:
    @pytest.mark.asyncio
    async def test_mock_evaluation_basic(self):
        client = MockGoAPIClient({"base_url": "http://mock", "evaluate_endpoint": "/test"})

        job = JobListing(
            id="test1",
            title="UX Designer",
            company="TestCorp",
            url="https://example.com",
            source=JobSource.LINKEDIN,
            description="Looking for a UX Designer with Figma experience.",
        )
        profile = ProfileSummary(
            name="Daniel",
            title="UX Designer",
            skills=["Figma", "UX Design", "Prototyping"],
            experience_years=5,
        )

        result = await client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["general.tex"],
            voice_samples=[],
        )

        assert 0 <= result.score <= 10
        assert result.adapted_cover_letter is not None
        assert len(result.adapted_cover_letter) > 50
        # Mock lowercases keywords
        assert any(k in result.matched_keywords for k in ["figma", "Figma"])

    @pytest.mark.asyncio
    async def test_mock_evaluation_no_match(self):
        client = MockGoAPIClient({})

        job = JobListing(
            id="test2",
            title="Nuclear Physicist",
            company="CERN",
            url="https://cern.ch",
            source=JobSource.INDEED,
            description="Quantum mechanics expert needed.",
        )
        profile = ProfileSummary(
            name="Daniel",
            title="UX Designer",
            skills=["Figma", "Design"],
            experience_years=5,
        )

        result = await client.evaluate(
            job=job, rejected=[], profile=profile,
            cv_variants=[], voice_samples=[],
        )

        assert result.score < 6  # Should be low since no skills match
        assert len(result.missing_keywords) > 0

    @pytest.mark.asyncio
    async def test_mock_english_output(self):
        client = MockGoAPIClient({})

        job = JobListing(
            id="test3",
            title="Product Owner",
            company="TechCorp",
            url="https://tech.com",
            source=JobSource.LINKEDIN,
            description="English speaking team.",
        )
        profile = ProfileSummary(
            name="Daniel", title="PO",
            skills=["Scrum"], experience_years=5,
        )

        result = await client.evaluate(
            job=job, rejected=[], profile=profile,
            cv_variants=[], voice_samples=[], language="en",
        )

        assert "Daniel Peters" in result.adapted_cover_letter
        assert "AI" in result.adapted_cover_letter or "KI" in result.adapted_cover_letter


class TestClientFactory:
    def test_create_real_client(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_API", "false")
        client = create_api_client({
            "base_url": "http://test",
            "evaluate_endpoint": "/evaluate",
            "timeout_seconds": 30,
        })
        assert isinstance(client, GoAPIClient)

    def test_create_mock_client(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK_API", "true")
        client = create_api_client({
            "base_url": "http://test",
            "evaluate_endpoint": "/evaluate",
            "timeout_seconds": 30,
        })
        assert isinstance(client, MockGoAPIClient)
