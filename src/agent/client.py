"""src/agent/client.py – Async httpx Client für Go-API + Mock-Server."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

from src.agent.schemas import (
    EvaluateRequest,
    EvaluateResponse,
    JobListing,
    ProfileSummary,
    RejectedJob,
)

logger = logging.getLogger("job-hunter")


class GoAPIClient:
    def __init__(self, config: dict) -> None:
        self.base_url = config["base_url"]
        self.evaluate_endpoint = config["evaluate_endpoint"]
        self.timeout = httpx.Timeout(config["timeout_seconds"], connect=5.0)
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def evaluate(
        self,
        job: JobListing,
        rejected: list[RejectedJob],
        profile: ProfileSummary,
        cv_variants: list[str],
        voice_samples: list[str],
        language: str = "de",
    ) -> EvaluateResponse:
        """Sendet Evaluations-Request an die Go-API."""
        request = EvaluateRequest(
            job=job,
            profile=profile,
            rejected_context=rejected,
            cv_variants=cv_variants,
            voice_samples=voice_samples,
            application_language=language,
        )

        try:
            response = await self.client.post(
                f"{self.base_url}{self.evaluate_endpoint}",
                json=request.model_dump(mode="json"),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            return EvaluateResponse.model_validate(data)

        except httpx.HTTPStatusError as e:
            logger.error(f"Go-API HTTP error: {e.response.status_code} – {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Go-API request failed: {e}")
            raise

    async def close(self) -> None:
        await self.client.aclose()


class MockGoAPIClient(GoAPIClient):
    """Mock-Client für lokale Entwicklung ohne Go-API."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.client = httpx.AsyncClient()  # dummy, never used

    async def evaluate(
        self,
        job: JobListing,
        rejected: list[RejectedJob],
        profile: ProfileSummary,
        cv_variants: list[str],
        voice_samples: list[str],
        language: str = "de",
    ) -> EvaluateResponse:
        """Liefert deterministische Mock-Responses basierend auf Job-Content."""
        logger.info("[MOCK] Evaluating job (no real Go-API connected)")

        # Simple heuristic scoring
        score = 5.0
        matched = []
        missing = []

        job_text = f"{job.title} {job.description}".lower()
        profile_skills = [s.lower() for s in profile.skills]

        for skill in profile_skills:
            if skill in job_text:
                score += 0.8
                matched.append(skill)
            else:
                missing.append(skill)

        # Cap at 10
        score = min(score, 10.0)

        # Mock cover letter (always ensure min length for validation)
        cover_letter = self._generate_mock_cover_letter(job, profile, language)
        if not cover_letter or len(cover_letter) < 50:
            cover_letter = (
                "Ich bin der KI-Bewerbungs-Agent von Daniel Peters. Mein System hat "
                "Ihre Ausschreibung analysiert und eine deutliche Passung zu seinem "
                "Profil ermittelt."
            )

        # Mock profile tip for top jobs
        profile_tip = None
        if score > 8.0 and missing:
            profile_tip = f"Erwägen Sie, '{missing[0]}' stärker im Profil zu betonen."

        return EvaluateResponse(
            score=round(score, 1),
            reasoning=f"Score basiert auf Keyword-Matching: {len(matched)} Skills gefunden.",
            adapted_cover_letter=cover_letter,
            matched_keywords=matched,
            missing_keywords=missing,
            profile_tip=profile_tip,
            agent_voice_confidence=0.7,
            selected_cv_variant=cv_variants[0] if cv_variants else None,
        )

    def _generate_mock_cover_letter(
        self,
        job: JobListing,
        profile: ProfileSummary,
        language: str,
    ) -> str:
        from src.agent.bullet_selector import BulletSelector
        selector = BulletSelector()
        top_bullets = selector.select(job.title, job.description, max_bullets=4, min_bullets=3)
        return _template_cover_letter(job, profile, top_bullets, language)

    async def close(self) -> None:
        pass


def create_api_client(config: dict) -> GoAPIClient:
    """Factory: Echte API oder Mock je nach Konfiguration."""
    if os.environ.get("USE_MOCK_API", "false").lower() == "true":
        logger.warning("Using MOCK Go-API client – no real API calls will be made")
        return MockGoAPIClient(config)
    return GoAPIClient(config)


def _template_cover_letter(
    job: JobListing,
    profile: ProfileSummary,
    bullets: list[str],
    language: str,
) -> str:
    """Fallback-Template wenn LLM nicht verfügbar.

    Strikt einsprachig, professionell mit Sie/you, 2-3 Absätze,
    konkrete Bullet-Beispiele als Fließtext eingewoben.
    """

    years = getattr(profile, "experience_years", None) or 7

    if language == "en":
        body = (
            f"I am the AI job application agent of Daniel Peters, writing on his behalf. "
            f"My system analysed your posting for {job.title} at {job.company} and identified "
            f"a strong match with his profile.\n\n"
            f"Daniel brings over {years} years of experience across design, product "
            f"ownership, and applied AI. "
        )
        if bullets:
            bullet_text = "; ".join(b.rstrip(".") for b in bullets[:3])
            body += f"His work covers {bullet_text}. "
        body += (
            f"\n\nWhat draws him to {job.company} is the opportunity to apply this experience "
            f"in a setting that values both craft and measurable impact."
        )
        return body

    body = (
        f"Ich bin der KI-Bewerbungs-Agent von Daniel Peters und schreibe Ihnen in seinem "
        f"Auftrag. Mein System hat Ihre Ausschreibung für {job.title} bei {job.company} "
        f"analysiert und eine deutliche Passung zu seinem Profil ermittelt.\n\n"
        f"Daniel bringt über {years} Jahre Berufserfahrung an der Schnittstelle von Design, "
        f"Produktverantwortung und angewandter künstlicher Intelligenz mit. "
    )
    if bullets:
        bullet_text = "; ".join(b.rstrip(".") for b in bullets[:3])
        body += f"Seine Arbeit umfasst {bullet_text}. "
    body += (
        f"\n\nWas ihn an {job.company} besonders anspricht, ist die Möglichkeit, diese "
        f"Erfahrung in einem Umfeld einzubringen, das sowohl gestalterische Qualität als "
        f"auch messbaren Impact verlangt."
    )
    return body
