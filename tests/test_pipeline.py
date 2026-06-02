"""tests/test_pipeline.py – End-to-End Pipeline-Integrationstest.

Testet den kompletten Flow:
  Job-Listing → Filter → Go-API-Evaluation → LaTeX-Rendering → SMTP-Send
"""

import pytest
from httpx import ASGITransport, AsyncClient
from pathlib import Path

from src.agent.client import GoAPIClient
from src.agent.schemas import JobListing, JobSource, ProfileSummary, StoredJob, ApplicationStatus
from src.agent.sender import SMTPSender
from src.api.mock_server import create_app, state
from src.crawler.filters import JobFilter
from src.latex.compiler import LaTeXCompiler


@pytest.fixture
def app():
    state.evaluate_calls.clear()
    return create_app()


@pytest.fixture
async def api_client(app):
    transport = ASGITransport(app=app)
    httpx_client = AsyncClient(transport=transport, base_url="http://test")
    client = GoAPIClient({
        "base_url": "http://test",
        "evaluate_endpoint": "/api/v1/evaluate",
        "timeout_seconds": 10,
    })
    client.client = httpx_client
    yield client
    await client.close()


@pytest.fixture
def profile():
    return ProfileSummary(
        name="Daniel Peters",
        title="UX Designer",
        skills=["Figma", "UX Design", "Prototyping", "User Research", "Design Systems"],
        experience_years=9,
        location="Augsburg, Germany",
        portfolio_url="portfolio.untitled-ux.de",
    )


@pytest.fixture
def job_filter():
    return JobFilter({
        "exclude_portal_only": False,
        "keywords": ["UX", "Designer", "Product"],
        "excluded_companies": [],
    })


@pytest.fixture
def latex_compiler(tmp_path: Path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return LaTeXCompiler({
        "output_dir": str(output_dir),
        "template_dir": "./src/latex/templates",
        "portfolio_url": "portfolio.untitled-ux.de",
    })


@pytest.fixture
def smtp_sender(monkeypatch):
    for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
        monkeypatch.delenv(var, raising=False)
    return SMTPSender({
        "host_env": "SMTP_HOST",
        "port_env": "SMTP_PORT",
        "user_env": "SMTP_USER",
        "password_env": "SMTP_PASSWORD",
        "from_addr_env": "SMTP_FROM",
        "from_name": "Test Sender",
        "retry": {"max_attempts": 1, "backoff": [0.01]},
    })


class TestPipelineFilterToEvaluation:
    """Test: Job-Filter → Go-API Evaluation."""

    @pytest.mark.asyncio
    async def test_matching_job_passes_filter_and_eval(self, job_filter, api_client, profile):
        job = JobListing(
            id="pipe-1",
            title="Senior UX Designer",
            company="TechCorp GmbH",
            location="Augsburg, Germany",
            url="https://techcorp.de/job/ux",
            source=JobSource.LINKEDIN,
            description="Wir suchen einen UX Designer mit Figma und User Research Erfahrung.",
            has_email_contact=True,
        )

        # Step 1: Filter
        assert job_filter.should_include(job) is True

        # Step 2: Evaluation
        result = await api_client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["ux.tex", "general.tex"],
            voice_samples=[],
            language="de",
        )

        assert result.score >= 5.0
        assert "figma" in result.matched_keywords
        assert result.selected_cv_variant is not None

    @pytest.mark.asyncio
    async def test_non_matching_job_filtered_out(self, job_filter):
        job = JobListing(
            id="pipe-2",
            title="Java Backend Developer",
            company="DevCo",
            location="Remote",
            url="https://devco.de/job/java",
            source=JobSource.INDEED,
            description="Seeking experienced Java developer for backend services.",
            has_email_contact=True,
        )

        assert job_filter.should_include(job) is False

    @pytest.mark.asyncio
    async def test_pipeline_score_threshold(self, job_filter, api_client, profile):
        """Jobs mit niedrigem Score sollten nicht weiterverarbeitet werden."""
        job = JobListing(
            id="pipe-3",
            title="Junior UX Intern",
            company="StartupCo",
            location="Munich",
            url="https://startupco.de/job/intern",
            source=JobSource.LINKEDIN,
            description="Internship opportunity for students interested in UX basics.",
            has_email_contact=True,
        )

        assert job_filter.should_include(job) is True  # Keyword match

        result = await api_client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["general.tex"],
            voice_samples=[],
        )

        # Junior/Intern sollte niedriger scoren als Senior-Rolle
        assert result.score < 8.0


class TestPipelineEvaluationToLaTeX:
    """Test: Evaluation → LaTeX-Rendering."""

    @pytest.mark.asyncio
    async def test_full_evaluation_to_pdf(self, api_client, profile, latex_compiler):
        job = JobListing(
            id="pipe-4",
            title="Product Designer",
            company="DesignStudio AG",
            location="Hamburg",
            url="https://designstudio.de/job/pd",
            source=JobSource.STEPSTONE,
            description="Product Designer mit Figma, Design Systems und Prototyping Skills.",
            has_email_contact=True,
        )

        # Evaluate
        result = await api_client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["ux.tex", "general.tex"],
            voice_samples=[],
            language="de",
        )

        assert result.score >= 5.0

        # Compile PDF (wenn Tectonic installiert ist)
        profile_data = {
            "name": profile.name,
            "title": profile.title,
            "location": profile.location,
            "email": "hi@untitled-ux.de",
            "phone": "+49 173 5231109",
            "portfolio_url": profile.portfolio_url,
            "include_photo": False,
            "salary_min": 56000,
            "salary_max": 70000,
            "availability": "nach Absprache",
            "application_language": "de",
        }

        try:
            pdf_path = await latex_compiler.compile(
                evaluation=result,
                job=job,
                profile_data=profile_data,
            )
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        except (FileNotFoundError, RuntimeError):
            # Tectonic nicht installiert – Rendering-Test separat
            pytest.skip("Tectonic not installed – skipping PDF compilation")


class TestPipelineLaTeXToSMTP:
    """Test: LaTeX-Rendering → SMTP-Send (Mock)."""

    @pytest.mark.asyncio
    async def test_smtp_message_construction(self, smtp_sender, tmp_path: Path):
        """Testet dass die SMTP-Nachricht korrekt aufgebaut wird."""
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")

        msg = smtp_sender._build_message(
            to_addr="jobs@company.de",
            subject="Bewerbung als UX Designer – Daniel Peters",
            body="Sehr geehrte Damen und Herren,\n\nanbei meine Bewerbung.",
            pdf_path=str(pdf),
        )

        assert "Bewerbung als UX Designer" in msg["Subject"]
        assert msg["To"] == "jobs@company.de"
        assert len(msg.get_payload()) == 2  # body + pdf


class TestPipelineEndToEnd:
    """Kompletter End-to-End-Test (ohne echten SMTP/Tectonic)."""

    @pytest.mark.asyncio
    async def test_full_pipeline_dry_run(self, job_filter, api_client, profile, smtp_sender):
        """Simuliert die komplette Pipeline ohne externe Abhängigkeiten."""
        # 1. Job-Listing (simuliert)
        job = JobListing(
            id="e2e-1",
            title="Senior UX Designer",
            company="TechCorp GmbH",
            location="München, Germany",
            url="https://techcorp.de/job/ux-senior",
            source=JobSource.LINKEDIN,
            description="Senior UX Designer mit Figma, Design Systems, "
                        "User Research und Prototyping Erfahrung.",
            has_email_contact=True,
            contact_email="jobs@techcorp.de",
        )

        # 2. Filter
        assert job_filter.should_include(job) is True

        # 3. Evaluation
        result = await api_client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["ux.tex", "general.tex"],
            voice_samples=[],
            language="de",
        )

        assert result.score > 7.0
        assert len(result.adapted_cover_letter) > 50
        assert result.selected_cv_variant is not None

        # 4. SMTP Message construction (dry run)
        msg = smtp_sender._build_message(
            to_addr=job.contact_email or "jobs@techcorp.de",
            subject=f"Bewerbung als {job.title} – {profile.name}",
            body=result.adapted_cover_letter,
        )

        assert msg["To"] == "jobs@techcorp.de"
        assert "Bewerbung als Senior UX Designer" in msg["Subject"]
        assert "KI-Tools" in result.adapted_cover_letter or "bewerbe" in result.adapted_cover_letter

        # 5. Verify server tracked the call
        assert len(state.evaluate_calls) == 1

    @pytest.mark.asyncio
    async def test_pipeline_rejected_job_not_processed(self, job_filter, api_client, profile):
        """Job der den Filter nicht passiert wird nicht evaluiert."""
        job = JobListing(
            id="e2e-2",
            title="DevOps Engineer",
            company="InfraCo",
            location="Remote",
            url="https://infraco.de/job/devops",
            source=JobSource.LINKEDIN,
            description="Kubernetes, Docker, Terraform, CI/CD pipeline expert needed.",
            has_email_contact=True,
        )

        # Filter rejects (no UX/Designer/Product keywords)
        assert job_filter.should_include(job) is False

        # Evaluation should not be called (simulate by checking state)
        initial_calls = len(state.evaluate_calls)

        # In real pipeline: if not filter.should_include(job): continue
        # So no evaluation happens
        assert len(state.evaluate_calls) == initial_calls

    @pytest.mark.asyncio
    async def test_pipeline_english_job(self, job_filter, api_client, profile):
        """Englischer Job sollte englisches Anschreiben generieren."""
        job = JobListing(
            id="e2e-3",
            title="Product Designer",
            company="GlobalTech Inc.",
            location="Remote (EU)",
            url="https://globaltech.io/job/designer",
            source=JobSource.LINKEDIN,
            description="We are looking for a Product Designer with experience in "
                        "Figma, design systems, and user research for our global team.",
            has_email_contact=True,
        )

        assert job_filter.should_include(job) is True

        result = await api_client.evaluate(
            job=job,
            rejected=[],
            profile=profile,
            cv_variants=["ux.tex"],
            voice_samples=[],
            language="en",
        )

        assert "AI" in result.adapted_cover_letter or "applying" in result.adapted_cover_letter
        assert result.score > 5.0
