#!/usr/bin/env python3
"""scripts/test_pipeline.py – Simuliert einen vollständigen Pipeline-Durchlauf."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("USE_MOCK_API", "true")

from src.agent.client import create_api_client
from src.agent.schemas import JobListing, JobSource, ProfileSummary
from src.crawler.filters import JobFilter
from src.database.init_db import init_database
from src.database.queries import JobRepository
from src.latex.compiler import LaTeXCompiler


async def test_pipeline():
    print("🧪 PIPELINE TEST")
    print("=" * 50)

    # 1. Config laden
    import yaml
    config = yaml.safe_load(open("data/config.yaml"))
    print("✅ Config geladen")

    # 2. DB initialisieren
    db_conn = await init_database()
    db = JobRepository(db_conn)
    print("✅ SQLite DB initialisiert")

    # 3. Mock API Client
    api_client = create_api_client(config["go_api"])
    print("✅ Mock API Client erstellt")

    # 4. Dummy Job erstellen
    job = JobListing(
        id="test_job_001",
        title="Senior UX Designer",
        company="TechCorp GmbH",
        location="Munich",
        url="https://example.com/job/123",
        source=JobSource.LINKEDIN,
        description="We are looking for a Senior UX Designer with 5+ years experience in Figma, Design Systems, and User Research. You will lead our design team and establish design processes.",
        requirements=["Figma", "Design Systems", "User Research", "5+ years"],
        has_email_contact=True,
    )
    print(f"✅ Dummy Job erstellt: {job.title} @ {job.company}")

    # 5. Filter testen
    filter_obj = JobFilter(config["search"])
    should_include = filter_obj.should_include(job)
    print(f"✅ Filter-Check: {'PASS' if should_include else 'FAIL'}")

    if not should_include:
        print("   Job wurde gefiltert – Test abgebrochen")
        return

    # 6. Profil laden
    profile = ProfileSummary(
        name="Daniel Peters",
        title="UX/UI Designer & Product Strategist",
        skills=["Figma", "UX Design", "UI Design", "Design Systems", "Prototyping", "User Research", "Scrum", "Agile"],
        experience_years=9,
        portfolio_url="portfolio.untitled-ux.de",
        linkedin_url="https://www.linkedin.com/in/daniel-peters-055296203/",
        languages=["Deutsch", "Englisch"],
    )
    print("✅ Profil geladen")

    # 7. Mock Evaluation
    result = await api_client.evaluate(
        job=job,
        rejected=[],
        profile=profile,
        cv_variants=["general.tex", "product_owner.tex"],
        voice_samples=[],
        language="de",
    )
    print(f"✅ Evaluation complete: Score={result.score}/10")
    print(f"   Matched: {result.matched_keywords}")
    print(f"   Missing: {result.missing_keywords}")
    print(f"   CV Variant: {result.selected_cv_variant}")
    if result.profile_tip:
        print(f"   💡 Profile Tip: {result.profile_tip}")

    # 8. Anschreiben Preview
    print("\n📄 ANSCHREIBEN PREVIEW:")
    print("-" * 50)
    print(result.adapted_cover_letter[:500] + "...")
    print("-" * 50)

    # 9. LaTeX Template Rendering (ohne tectonic)
    compiler = LaTeXCompiler(config["latex"])
    
    # Template laden und rendern
    from jinja2 import Environment
    latex_env = Environment(
        block_start_string="<%", block_end_string="%>",
        variable_start_string="<<", variable_end_string=">>",
    )
    
    template_path = Path("src/latex/templates/cover_letter.tex")
    template_text = template_path.read_text(encoding="utf-8")
    template = latex_env.from_string(template_text)
    
    profile_data = profile.model_dump()
    profile_data.update({
        "applicant_email": "hi@untitled-ux.de",
        "applicant_phone": "+49 173 5231109",
        "applicant_location": "Augsburg, Germany",
        "job_title": job.title,
        "company": job.company,
        "job_location": job.location,
        "job_url": str(job.url),
        "cover_letter_body": result.adapted_cover_letter,
        "score": result.score,
        "date": "\\today",
        "include_photo": False,
        "photo_path": "",
        "salary_expectation": "",
        "salary_min": 56000,
        "salary_max": 70000,
        "availability": "nach Absprache",
        "application_language": "de",
    })
    
    rendered = template.render(profile_data)
    print("\n📐 LaTeX TEMPLATE RENDERED:")
    print("-" * 50)
    print(rendered[:800] + "...")
    print("-" * 50)

    # 10. DB Operationen testen
    from src.agent.schemas import StoredJob, ApplicationStatus
    stored = StoredJob(
        id=job.id,
        title=job.title,
        company=job.company,
        url=str(job.url),
        source=job.source,
        score=result.score,
        status=ApplicationStatus.PENDING,
        cv_variant=result.selected_cv_variant,
    )
    await db.store_job(stored, job_hash=f"hash_{job.id}")
    print("✅ Job in SQLite gespeichert")

    retrieved = await db.get_job(job.id)
    print(f"✅ Job aus DB gelesen: {retrieved.title} (Score: {retrieved.score})")

    # 11. Agent State
    from src.agent.schemas import AgentState
    state = await db.get_agent_state()
    print(f"✅ Agent State: paused={state.paused}, quiet={state.quiet_mode}")

    await api_client.close()
    await db.close()

    print("\n" + "=" * 50)
    print("🎉 PIPELINE TEST COMPLETE – Alles funktioniert!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_pipeline())
