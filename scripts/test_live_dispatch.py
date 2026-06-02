#!/usr/bin/env python3
"""scripts/test_live_dispatch.py – Sendet einen simulierten Job-Vorschlag an den Telegram-Bot."""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("USE_MOCK_API", "true")

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot
from src.agent.client import create_api_client
from src.agent.schemas import JobListing, JobSource, ProfileSummary, StoredJob, ApplicationStatus
from src.database.init_db import init_database
from src.database.queries import JobRepository
from src.telegram.formatters import format_job_proposal
from src.telegram.keyboards import job_proposal_keyboard

async def test_live_dispatch():
    print("📲 LIVE DISPATCH TEST")
    print("=" * 50)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", 0))

    if not token or not chat_id:
        print("❌ Token oder Chat ID fehlt!")
        return

    bot = Bot(token=token)

    # Dummy Job
    job = JobListing(
        id="live_test_001",
        title="Senior Product Designer",
        company="Awesome Startup",
        location="Berlin (Hybrid)",
        url="https://linkedin.com/jobs/123",
        source=JobSource.LINKEDIN,
        description="We are looking for a Senior Product Designer to lead our design team. You will work on B2B SaaS products with Figma, Design Systems, and User Research.",
        requirements=["Figma", "Design Systems", "User Research", "B2B SaaS"],
        has_email_contact=True,
    )

    # Mock Evaluation
    api_client = create_api_client({"base_url": "http://mock", "evaluate_endpoint": "/test", "timeout_seconds": 30})
    profile = ProfileSummary(
        name="Daniel Peters",
        title="UX/UI Designer & Product Strategist",
        skills=["Figma", "UX Design", "UI Design", "Design Systems", "Prototyping", "User Research", "Scrum"],
        experience_years=9,
    )

    result = await api_client.evaluate(
        job=job, rejected=[], profile=profile,
        cv_variants=["general.tex"], voice_samples=[], language="de",
    )

    print(f"✅ Evaluation: Score {result.score}/10")

    # In DB speichern
    db_conn = await init_database()
    db = JobRepository(db_conn)
    stored = StoredJob(
        id=job.id, title=job.title, company=job.company,
        url=str(job.url), source=job.source, score=result.score,
        status=ApplicationStatus.PENDING,
    )
    await db.store_job(stored)

    # Telegram Nachricht senden
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

    print(f"✅ Nachricht an Chat {chat_id} gesendet!")
    print("   👉 Prüfe dein Telegram!")

    await api_client.close()
    await db.close()
    await bot.session.close()

    print("=" * 50)
    print("🎉 LIVE TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(test_live_dispatch())
