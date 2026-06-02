"""tests/test_mock_server.py – Tests für den FastAPI Mock Go-API Server."""

import pytest
from httpx import AsyncClient, ASGITransport

from src.api.mock_server import create_app, state


@pytest.fixture
def app():
    """Erstellt eine frische App-Instanz pro Test."""
    # Reset state before each test
    state.evaluate_calls.clear()
    state.cover_letter_calls.clear()
    state.cv_selection_calls.clear()
    state.duplicate_checks.clear()
    state.follow_up_calls.clear()
    return create_app()


@pytest.fixture
async def client(app):
    """Async-HTTP-Client für FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "evaluate_calls" in data


class TestEvaluateEndpoint:
    @pytest.mark.asyncio
    async def test_evaluate_basic_match(self, client):
        body = {
            "job": {
                "id": "job1",
                "title": "Senior UX Designer",
                "company": "TechCorp",
                "location": "Berlin",
                "url": "https://techcorp.de/job",
                "source": "linkedin",
                "description": "We need an experienced UX Designer with Figma skills.",
            },
            "profile": {
                "name": "Daniel Peters",
                "title": "UX Designer",
                "skills": ["Figma", "UX Design", "Prototyping", "User Research"],
                "experience_years": 9,
            },
            "cv_variants": ["ux.tex", "general.tex", "backend.tex"],
            "application_language": "de",
        }

        response = await client.post("/api/v1/evaluate", json=body)
        assert response.status_code == 200

        data = response.json()
        assert 0 <= data["score"] <= 10
        assert len(data["adapted_cover_letter"]) > 50
        assert "figma" in data["matched_keywords"]
        assert data["selected_cv_variant"] is not None
        assert "ux" in data["selected_cv_variant"].lower()

    @pytest.mark.asyncio
    async def test_evaluate_no_match(self, client):
        body = {
            "job": {
                "id": "job2",
                "title": "Nuclear Physicist",
                "company": "CERN",
                "location": "Geneva",
                "url": "https://cern.ch/job",
                "source": "linkedin",
                "description": "Quantum mechanics expert needed for particle physics.",
            },
            "profile": {
                "name": "Daniel",
                "title": "UX Designer",
                "skills": ["Figma", "Design"],
                "experience_years": 5,
            },
            "cv_variants": ["general.tex"],
            "application_language": "de",
        }

        response = await client.post("/api/v1/evaluate", json=body)
        assert response.status_code == 200

        data = response.json()
        assert data["score"] < 7  # Low score for no match
        assert len(data["missing_keywords"]) > 0

    @pytest.mark.asyncio
    async def test_evaluate_english_output(self, client):
        body = {
            "job": {
                "id": "job3",
                "title": "Product Designer",
                "company": "TechCo",
                "location": "Remote",
                "url": "https://techco.com/job",
                "source": "linkedin",
                "description": "Join our international team as a Product Designer.",
            },
            "profile": {
                "name": "Daniel Peters",
                "title": "Designer",
                "skills": ["Figma"],
                "experience_years": 5,
            },
            "cv_variants": ["general.tex"],
            "application_language": "en",
        }

        response = await client.post("/api/v1/evaluate", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "KI-Tools" in data["adapted_cover_letter"] or "AI" in data["adapted_cover_letter"]

    @pytest.mark.asyncio
    async def test_evaluate_tracks_calls(self, client):
        body = {
            "job": {
                "id": "job4",
                "title": "Test",
                "company": "Co",
                "location": "Remote",
                "url": "https://co.de",
                "source": "linkedin",
                "description": "Test description with enough content for evaluation.",
            },
            "profile": {
                "name": "Test",
                "title": "Dev",
                "skills": ["Python"],
                "experience_years": 3,
            },
            "cv_variants": ["general.tex"],
        }

        await client.post("/api/v1/evaluate", json=body)
        await client.post("/api/v1/evaluate", json=body)

        assert len(state.evaluate_calls) == 2

    @pytest.mark.asyncio
    async def test_evaluate_profile_tip_for_top_jobs(self, client):
        body = {
            "job": {
                "id": "job5",
                "title": "Senior UX Designer",
                "company": "TopCorp",
                "location": "Berlin",
                "url": "https://topcorp.de/job",
                "source": "linkedin",
                "description": "Figma, UX Design, Prototyping, User Research, Design Systems, "
                             "Accessibility, WCAG, A/B Testing, Analytics, Leadership.",
            },
            "profile": {
                "name": "Daniel",
                "title": "UX Designer",
                "skills": ["Figma", "UX Design", "Prototyping", "User Research", "Design Systems", "React"],
                "experience_years": 9,
            },
            "cv_variants": ["ux.tex"],
            "application_language": "de",
        }

        response = await client.post("/api/v1/evaluate", json=body)
        data = response.json()

        # Many skills matched → high score → profile tip (React won't match)
        assert data["score"] > 8.0
        assert data["profile_tip"] is not None
        assert "react" in data["missing_keywords"]


class TestCoverLetterEndpoint:
    @pytest.mark.asyncio
    async def test_generate_cover_letter_german(self, client):
        body = {
            "job": {
                "title": "UX Designer",
                "company": "TestCorp",
                "location": "Berlin",
            },
            "profile": {
                "name": "Daniel Peters",
                "skills": ["Figma"],
            },
            "language": "de",
        }

        response = await client.post("/api/v1/generate-cover-letter", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "KI-Tools" in data["cover_letter"]
        assert "Bewerbung als UX Designer" in data["subject"]

    @pytest.mark.asyncio
    async def test_generate_cover_letter_english(self, client):
        body = {
            "job": {
                "title": "Product Designer",
                "company": "TechCo",
                "location": "Remote",
            },
            "profile": {
                "name": "Daniel",
                "skills": ["Figma"],
            },
            "language": "en",
        }

        response = await client.post("/api/v1/generate-cover-letter", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "AI" in data["cover_letter"] or "applying" in data["cover_letter"]


class TestSelectCVEndpoint:
    @pytest.mark.asyncio
    async def test_select_cv_backend(self, client):
        body = {
            "job": {
                "title": "Senior Backend Engineer",
                "company": "TechCorp",
            },
            "available_cvs": ["backend.tex", "frontend.tex", "general.tex"],
        }

        response = await client.post("/api/v1/select-cv", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "backend" in data["selected_cv"].lower()

    @pytest.mark.asyncio
    async def test_select_cv_devops(self, client):
        body = {
            "job": {
                "title": "DevOps Engineer",
                "company": "CloudCo",
            },
            "available_cvs": ["devops.tex", "backend.tex", "general.tex"],
        }

        response = await client.post("/api/v1/select-cv", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "devops" in data["selected_cv"].lower()

    @pytest.mark.asyncio
    async def test_select_cv_fallback(self, client):
        body = {
            "job": {
                "title": "Janitor",
                "company": "CleanCo",
            },
            "available_cvs": ["backend.tex", "frontend.tex"],
        }

        response = await client.post("/api/v1/select-cv", json=body)
        assert response.status_code == 200

        data = response.json()
        assert data["selected_cv"] == "backend.tex"  # First available


class TestDuplicateCheckEndpoint:
    @pytest.mark.asyncio
    async def test_duplicate_same_job(self, client):
        body = {
            "job_a": {
                "title": "UX Designer",
                "company": "TechCorp",
            },
            "job_b": {
                "title": "UX Designer",
                "company": "TechCorp",
            },
        }

        response = await client.post("/api/v1/check-duplicate", json=body)
        assert response.status_code == 200

        data = response.json()
        assert data["is_duplicate"] is True
        assert data["confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_not_duplicate_different_jobs(self, client):
        body = {
            "job_a": {
                "title": "UX Designer",
                "company": "TechCorp",
            },
            "job_b": {
                "title": "Backend Engineer",
                "company": "OtherCo",
            },
        }

        response = await client.post("/api/v1/check-duplicate", json=body)
        assert response.status_code == 200

        data = response.json()
        assert data["is_duplicate"] is False


class TestFollowUpEndpoint:
    @pytest.mark.asyncio
    async def test_generate_follow_up(self, client):
        body = {
            "job": {
                "title": "UX Designer",
                "company": "TechCorp",
            },
            "original_cover_letter": "Original text...",
            "days_since": 10,
        }

        response = await client.post("/api/v1/generate-follow-up", json=body)
        assert response.status_code == 200

        data = response.json()
        assert "vor 10 Tagen" in data["follow_up_text"]
        assert "TechCorp" in data["follow_up_text"]


class TestStatsEndpoint:
    @pytest.mark.asyncio
    async def test_stats_tracks_all_calls(self, client):
        # Make some calls
        eval_body = {
            "job": {
                "id": "1", "title": "Test", "company": "Co",
                "location": "Remote", "url": "https://co.de",
                "source": "linkedin", "description": "Test description with enough content.",
            },
            "profile": {"name": "T", "title": "D", "skills": ["S"], "experience_years": 1},
            "cv_variants": ["general.tex"],
        }

        await client.post("/api/v1/evaluate", json=eval_body)
        await client.post("/api/v1/evaluate", json=eval_body)
        await client.post("/api/v1/select-cv", json={
            "job": {"title": "Test", "company": "Co"},
            "available_cvs": ["general.tex"],
        })

        response = await client.get("/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["evaluate_calls"] == 2
        assert data["cv_selection_calls"] == 1
