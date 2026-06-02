"""src/api/mock_server.py – FastAPI Mock-Server für Go-API Contract-Tests."""

from __future__ import annotations

import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger("job-hunter")


# ── In-Memory State ──────────────────────────────────────────────

class MockState:
    def __init__(self) -> None:
        self.evaluate_calls: list[dict] = []
        self.cover_letter_calls: list[dict] = []
        self.cv_selection_calls: list[dict] = []
        self.duplicate_checks: list[dict] = []
        self.follow_up_calls: list[dict] = []


state = MockState()


# ── App Factory ──────────────────────────────────────────────────

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Mock Go-API server started on http://localhost:8080")
        yield
        logger.info("Mock Go-API server stopped")

    app = FastAPI(
        title="Job Hunter Go-API Mock",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── POST /api/v1/evaluate ────────────────────────────────────────

    @app.post("/api/v1/evaluate")
    async def evaluate(body: dict) -> dict:
        """Evaluates a job against the profile and returns scoring + cover letter."""
        state.evaluate_calls.append(body)

        job = body.get("job", {})
        profile = body.get("profile", {})
        cv_variants = body.get("cv_variants", [])
        language = body.get("application_language", "de")

        job_text = f"{job.get('title', '')} {job.get('description', '')}".lower()
        profile_skills = [s.lower() for s in profile.get("skills", [])]

        # Keyword scoring
        matched = [s for s in profile_skills if s in job_text]
        missing = [s for s in profile_skills if s not in job_text]

        score = 5.0 + (len(matched) * 0.8)
        score = min(round(score, 1), 10.0)

        # CV variant selection
        selected_cv = _select_cv(job, cv_variants)

        # Cover letter generation
        cover_letter = _generate_cover_letter(job, profile, language, matched)

        # Profile tip for top jobs
        profile_tip = None
        if score > 8.0 and missing:
            profile_tip = f"Erwägen Sie, '{missing[0]}' stärker im Profil zu betonen."

        return {
            "score": score,
            "reasoning": f"Score basiert auf Keyword-Matching: {len(matched)} von {len(profile_skills)} Skills gefunden.",
            "adapted_cover_letter": cover_letter,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "profile_tip": profile_tip,
            "agent_voice_confidence": round(random.uniform(0.7, 0.95), 2),
            "selected_cv_variant": selected_cv,
            "is_duplicate_of": None,
        }

    # ── POST /api/v1/generate-cover-letter ───────────────────────────

    @app.post("/api/v1/generate-cover-letter")
    async def generate_cover_letter(body: dict) -> dict:
        """Generiert ein personalisiertes Anschreiben."""
        state.cover_letter_calls.append(body)

        job = body.get("job", {})
        profile = body.get("profile", {})
        language = body.get("language", "de")

        cover_letter = _generate_cover_letter(job, profile, language, [])
        subject = f"Bewerbung als {job.get('title', 'Unbekannt')} – {profile.get('name', 'Bewerber')}"

        return {
            "cover_letter": cover_letter,
            "subject": subject,
        }

    # ── POST /api/v1/select-cv ───────────────────────────────────────

    @app.post("/api/v1/select-cv")
    async def select_cv(body: dict) -> dict:
        """Wählt die passende CV-Variante aus."""
        state.cv_selection_calls.append(body)

        job = body.get("job", {})
        available_cvs = body.get("available_cvs", [])

        selected = _select_cv(job, available_cvs)
        reason = f"CV '{selected}' passt am besten zu {job.get('title', 'der Stelle')}."

        return {
            "selected_cv": selected,
            "reason": reason,
        }

    # ── POST /api/v1/check-duplicate ─────────────────────────────────

    @app.post("/api/v1/check-duplicate")
    async def check_duplicate(body: dict) -> dict:
        """Prüft ob zwei Jobs Duplikate sind."""
        state.duplicate_checks.append(body)

        job_a = body.get("job_a", {})
        job_b = body.get("job_b", {})

        # Simple heuristic: same title + company = likely duplicate
        title_match = job_a.get("title", "").lower() == job_b.get("title", "").lower()
        company_match = job_a.get("company", "").lower() == job_b.get("company", "").lower()

        is_duplicate = title_match and company_match
        confidence = 0.95 if is_duplicate else 0.2

        return {
            "is_duplicate": is_duplicate,
            "confidence": confidence,
        }

    # ── POST /api/v1/generate-follow-up ──────────────────────────────

    @app.post("/api/v1/generate-follow-up")
    async def generate_follow_up(body: dict) -> dict:
        """Generiert Follow-up-Text."""
        state.follow_up_calls.append(body)

        job = body.get("job", {})
        days_since = body.get("days_since", 7)

        follow_up_text = (
            f"Sehr geehrte Damen und Herren,\n\n"
            f"vor {days_since} Tagen habe ich mich bei Ihnen als "
            f"{job.get('title', 'Bewerber')} beworben. "
            f"Ich möchte mich nach dem aktuellen Stand meiner Bewerbung erkundigen "
            f"und mein fortwährendes Interesse an der Position bei "
            f"{job.get('company', 'Ihrem Unternehmen')} bekräftigen.\n\n"
            f"Über eine Rückmeldung freue ich mich sehr.\n\n"
            f"Mit freundlichen Grüßen"
        )

        return {
            "follow_up_text": follow_up_text,
        }

    # ── GET /health ──────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "healthy",
            "evaluate_calls": len(state.evaluate_calls),
            "cover_letter_calls": len(state.cover_letter_calls),
        }

    # ── GET /stats ───────────────────────────────────────────────────

    @app.get("/stats")
    async def stats() -> dict:
        return {
            "evaluate_calls": len(state.evaluate_calls),
            "cover_letter_calls": len(state.cover_letter_calls),
            "cv_selection_calls": len(state.cv_selection_calls),
            "duplicate_checks": len(state.duplicate_checks),
            "follow_up_calls": len(state.follow_up_calls),
        }

    return app


# ── Helpers ──────────────────────────────────────────────────────

def _select_cv(job: dict, cv_variants: list[str]) -> str | None:
    """Wählt CV-Variante basierend auf Job-Titel."""
    if not cv_variants:
        return None

    title = job.get("title", "").lower()

    cv_mapping = {
        "backend": ["backend", "server", "api", "python", "java", "go"],
        "frontend": ["frontend", "front-end", "ui", "react", "angular", "vue"],
        "fullstack": ["fullstack", "full-stack", "full stack"],
        "devops": ["devops", "dev-ops", "infrastructure", "kubernetes", "docker", "ci/cd"],
        "data": ["data engineer", "data scientist", "data analyst", "etl", "spark"],
        "ai": ["ai", "machine learning", "ml", "deep learning", "nlp"],
        "ux": ["ux", "design", "product design", "user experience"],
    }

    for cv_name, keywords in cv_mapping.items():
        if any(kw in title for kw in keywords):
            # Find matching variant in available list
            for variant in cv_variants:
                if cv_name in variant.lower():
                    return variant

    return cv_variants[0]  # Fallback to first


def _generate_cover_letter(
    job: dict,
    profile: dict,
    language: str,
    matched_skills: list[str],
) -> str:
    """Generiert ein Anschreiben basierend auf Job und Profil."""
    name = profile.get("name", "Bewerber")
    company = job.get("company", "das Unternehmen")
    title = job.get("title", "die Position")
    location = job.get("location", "Remote")
    skills_str = ", ".join(matched_skills[:3]) if matched_skills else "meine bisherigen Erfahrungen"

    if language == "en":
        return (
            f"Dear Hiring Team at {company},\n\n"
            f"I am applying for the {title} position at {company}. "
            f"I build AI-powered application agents as part of my core workflow "
            f"-- this letter was generated by my own system.\n\n"
            f"Key results from my work across consulting and freelance projects:\n\n"
            f"{skills_str}\n\n"
            f"I work daily with AI tools in production -- "
            f"not as a gimmick, but as a real productivity multiplier."
        )

    return (
        f"ich bewerbe mich hiermit auf die Position als {title} bei {company} in {location}. "
        f"Meine Expertise in {skills_str} sowie meine tägliche Arbeit mit KI-Tools "
        f"machen mich zu einem guten Match.\n\n"
        f"Konkrete Ergebnisse aus Beratungs- und Freelance-Projekten:\n\n"
        f"• {skills_str}"
    )


# ── Entry Point ──────────────────────────────────────────────────

def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Startet den Mock-Server."""
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
