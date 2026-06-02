#!/usr/bin/env python3
"""scripts/test_full_pipeline.py – Kompletter Pipeline-Test mit Dummy-Jobs."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("USE_MOCK_API", "true")

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot

from src.agent.client import create_api_client
from src.agent.schemas import (
    JobListing, JobSource, ProfileSummary, StoredJob,
    ApplicationStatus, AgentState, AuditLogEntry
)
from src.crawler.filters import JobFilter
from src.database.init_db import init_database
from src.database.queries import JobRepository
from src.latex.compiler import LaTeXCompiler
from src.telegram.formatters import format_job_proposal
from src.telegram.keyboards import job_proposal_keyboard


# Dummy Jobs (simulieren echte JobSpy-Daten)
DUMMY_JOBS = [
    JobListing(
        id="linkedin_001",
        title="Senior UX Designer",
        company="Audi AG",
        location="Ingolstadt",
        url="https://linkedin.com/jobs/audi-ux-001",
        source=JobSource.LINKEDIN,
        description="We are looking for a Senior UX Designer to lead our digital product design team. You will work on automotive interfaces, design systems, and user research. Experience with Figma, agile methods, and stakeholder management required.",
        requirements=["Figma", "Design Systems", "User Research", "Agile", "5+ years"],
        has_email_contact=True,
        contact_email="jobs@audi.com",
    ),
    JobListing(
        id="stepstone_001",
        title="Product Owner Digital",
        company="BMW Group",
        location="Munich",
        url="https://stepstone.de/jobs/bmw-po-001",
        source=JobSource.STEPSTONE,
        description="Product Owner for digital services. Responsible for roadmap, backlog prioritization, and stakeholder alignment. SAFe/Scrum experience preferred. Automotive background a plus.",
        requirements=["Product Owner", "Scrum", "SAFe", "Jira", "Roadmap"],
        has_email_contact=True,
        contact_email="careers@bmwgroup.de",
    ),
    JobListing(
        id="indeed_001",
        title="UX/UI Designer",
        company="StartUp GmbH",
        location="Berlin (Remote)",
        url="https://indeed.com/jobs/startup-ux-001",
        source=JobSource.INDEED,
        description="Young startup looking for a versatile UX/UI Designer. WordPress, Webflow, and Figma skills needed. Quick prototyping and branding experience welcome.",
        requirements=["Figma", "Webflow", "WordPress", "Branding"],
        has_email_contact=False,  # Portal-only → soll gefiltert werden
    ),
]


async def test_full_pipeline():
    print("🚀 VOLLSTÄNDIGER PIPELINE TEST")
    print("=" * 60)

    # 1. Config laden
    import yaml
    config = yaml.safe_load(open("data/config.yaml"))
    print("✅ Config geladen")

    # 2. DB initialisieren
    db_conn = await init_database()
    db = JobRepository(db_conn)
    print("✅ SQLite DB initialisiert")

    # 3. API Client
    api_client = create_api_client(config["go_api"])
    print("✅ Mock API Client bereit")

    # 4. LaTeX Compiler
    compiler = LaTeXCompiler(config["latex"])
    print("✅ LaTeX Compiler bereit")

    # 5. Telegram Bot
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", 0))
    bot = Bot(token=token)
    print(f"✅ Telegram Bot verbunden (Chat: {chat_id})")

    # 6. Profil
    profile = ProfileSummary(
        name="Daniel Peters",
        title="UX/UI Designer & Product Strategist",
        skills=["Figma", "UX Design", "UI Design", "Design Systems", "Prototyping", 
                "User Research", "Scrum", "Agile", "Product Ownership", "Webflow"],
        experience_years=9,
        portfolio_url="portfolio.untitled-ux.de",
        linkedin_url="https://www.linkedin.com/in/daniel-peters-055296203/",
        languages=["Deutsch", "Englisch"],
    )
    print("✅ Profil geladen")

    # 7. Filter
    filter_obj = JobFilter(config["search"])

    # 8. Pipeline durchlaufen
    jobs_processed = 0
    jobs_sent = 0

    for job in DUMMY_JOBS:
        print(f"\n📋 Job: {job.title} @ {job.company}")
        print(f"   Quelle: {job.source.value} | Ort: {job.location}")

        # Filter
        if not filter_obj.should_include(job):
            print(f"   ⏭️ GEFILTERT (Portal-only oder Keyword-Mismatch)")
            continue

        # Evaluierung
        result = await api_client.evaluate(
            job=job, rejected=[], profile=profile,
            cv_variants=["general.tex"], voice_samples=[], language="de",
        )
        print(f"   ⭐ Score: {result.score}/10")
        print(f"   🎯 Matched: {result.matched_keywords}")

        # Score Check
        if result.score < config["thresholds"]["min_score"]:
            print(f"   ⏭️ Zu niedrig (Min: {config['thresholds']['min_score']})")
            continue

        # PDF generieren
        try:
            profile_data = profile.model_dump()
            profile_data.update({
                "applicant_email": os.environ.get("SMTP_FROM", "djdanep@gmail.com"),
                "applicant_phone": "+49 173 5231109",
                "applicant_location": "Augsburg, Germany",
                "job_title": job.title,
                "company": job.company,
                "job_location": job.location,
                "job_url": str(job.url),
                "cover_letter_body": result.adapted_cover_letter,
                "score": result.score,
                "date": "\\today",
                "include_photo": config["agent"]["include_photo"],
                "photo_path": config["cv"]["photo_path"],
                "salary_expectation": "",
                "salary_min": config["cv"]["salary_range"]["min"],
                "salary_max": config["cv"]["salary_range"]["max"],
                "availability": "nach Absprache",
                "application_language": "de",
            })

            # Prüfe ob tectonic verfügbar
            import shutil
            if shutil.which("tectonic"):
                pdf_path = await compiler.compile(
                    evaluation=result, job=job, profile_data=profile_data
                )
                print(f"   📄 PDF generiert: {pdf_path}")
            else:
                print(f"   ⚠️ Tectonic nicht installiert – PDF-Skipped")
                pdf_path = None

        except Exception as e:
            print(f"   ⚠️ PDF-Fehler: {e}")
            pdf_path = None

        # In DB speichern
        stored = StoredJob(
            id=job.id, title=job.title, company=job.company,
            url=str(job.url), source=job.source, score=result.score,
            status=ApplicationStatus.PENDING, cv_variant=result.selected_cv_variant,
        )
        await db.store_job(stored, job_hash=f"hash_{job.id}")

        # Telegram senden
        text = format_job_proposal(
            title=job.title, company=job.company, score=result.score,
            location=job.location, source=job.source.value,
            skills=result.matched_keywords,
        )

        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=job_proposal_keyboard(job.id),
        )

        # Anschreiben als separate Nachricht
        cover_preview = result.adapted_cover_letter[:800]
        await bot.send_message(
            chat_id=chat_id,
            text=f"*Anschreiben (Vorschau):*\n\n{cover_preview}...",
        )

        # Wenn PDF vorhanden, auch als Dokument senden
        if pdf_path and Path(pdf_path).exists():
            from aiogram.types import FSInputFile
            pdf_file = FSInputFile(pdf_path)
            await bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                caption=f"📎 Bewerbung: {job.title} @ {job.company}",
            )

        print(f"   ✅ AN TELEGRAM GESENDET!")
        jobs_sent += 1

        # Audit Log
        await db.log_event(AuditLogEntry(
            event_type="job_proposed",
            job_id=job.id,
            details=f"Score: {result.score}, CV: {result.selected_cv_variant}",
        ))

        jobs_processed += 1

        # Kurze Pause zwischen Jobs
        await asyncio.sleep(1)

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("📊 PIPELINE ZUSAMMENFASSUNG")
    print(f"   Jobs gescannt: {len(DUMMY_JOBS)}")
    print(f"   Nach Filter: {jobs_processed}")
    print(f"   An Telegram gesendet: {jobs_sent}")
    print(f"   Rejects: 0")
    print("=" * 60)
    print("🎉 ERSTER DURCHLAUF COMPLETE!")
    print("   👉 Prüfe dein Telegram für die Job-Vorschläge!")

    # Cleanup
    await api_client.close()
    await db.close()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
