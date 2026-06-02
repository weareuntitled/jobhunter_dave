"""src/main.py – Orchestrierung: asyncio Loop + aiogram Bot."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytz
import yaml
from dotenv import load_dotenv
load_dotenv()

from src.agent.client import create_api_client
from src.agent.bullet_selector import BulletSelector
from src.agent.schemas import AgentState, ApplicationStatus, AuditLogEntry, StoredJob
from src.agent.sender import SMTPSender
from src.crawler.scraper import JobScraper
from src.database.init_db import init_database
from src.database.queries import JobRepository
from src.latex.compiler import LaTeXCompiler
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.telegram.bot import create_bot, set_bot_commands
from src.telegram.routers import briefing, feedback, jobs, hunt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("job-hunter")

CONFIG_PATH = Path("data/config.yaml")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Shared Application State ──────────────────────────────────────

class AppState:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.db: JobRepository | None = None
        self.scraper: JobScraper | None = None
        self.api_client = None
        self.compiler: LaTeXCompiler | None = None
        self.smtp: SMTPSender | None = None
        self.bullet_selector: BulletSelector | None = None
        self.bot = None
        self.dispatcher = None

    async def initialize(self) -> None:
        self.db = JobRepository(await init_database())
        # Scraper bekommt Referenz auf search-config (für Keyword-Override)
        search_config = self.config["search"]
        search_config.update(self.config.get("filtering", {}))
        self.scraper = JobScraper(search_config)
        self.api_client = create_api_client(self.config["go_api"])
        self.compiler = LaTeXCompiler(self.config["latex"])
        self.smtp = SMTPSender(self.config["smtp"])
        self.bullet_selector = BulletSelector()
        self.bot, self.dispatcher = create_bot(self.config["telegram"])

        # Router registrieren
        self.dispatcher.include_router(jobs.router)
        self.dispatcher.include_router(feedback.router)
        self.dispatcher.include_router(briefing.router)
        self.dispatcher.include_router(hunt.router)

        # Dependency-Injection für Router
        self.dispatcher["db"] = self.db
        self.dispatcher["smtp"] = self.smtp
        self.dispatcher["app"] = self

        # Auto-Hunt on Startup (Phase 6, Feature 28)
        asyncio.create_task(self._auto_hunt_on_startup())

        logger.info("✅ AppState initialized – all components ready")

    async def _auto_hunt_on_startup(self) -> None:
        """Startet einen Hunt-Cycle nach Bot-Start + launcht Scheduler-Loop."""
        await asyncio.sleep(5)
        chat_id = int(os.environ.get(self.config["telegram"]["chat_id_env"], 0))
        if not chat_id or not self.bot:
            logger.info("⚠️ Kein chat_id – Auto-Hunt übersprungen")
            return

        await self.bot.send_message(chat_id, "🔍 <b>Starte Job-Suche...</b>")
        agent_state = await self.db.get_agent_state()
        # Auto-Hunt: immer quiet mode (keine Einzel-Jobs)
        saved_quiet = agent_state.quiet_mode
        agent_state.quiet_mode = True
        await self.db.update_agent_state(agent_state)
        found = await run_hunt_cycle(self, chat_id)
        agent_state.quiet_mode = saved_quiet
        await self.db.update_agent_state(agent_state)
        if found:
            await self.bot.send_message(chat_id, f"✅ <b>{found} neue Jobs</b> gefunden. /jobs für Details.")
        else:
            await self.bot.send_message(chat_id, "😕 Keine neuen Jobs.")
        logger.info(f"🚀 Auto-Hunt: {found} jobs found")
    
    async def _scheduler_loop(self) -> None:
        """Ewiger Loop: hunt → schlaf → hunt → …"""
        interval = self.config["schedule"]["hunt_interval_minutes"]
        chat_id = int(os.environ.get(self.config["telegram"]["chat_id_env"], 0))
        if not chat_id or not self.bot:
            logger.info("⚠️ Scheduler: kein chat_id, loop gestoppt")
            return
        
        while True:
            await asyncio.sleep(interval * 60)
            try:
                agent_state = await self.db.get_agent_state()
                if agent_state.paused:
                    continue
                if not _is_active_hour(self.config):
                    continue
                # Scheduler-Hunt: immer quiet mode
                saved_quiet = agent_state.quiet_mode
                agent_state.quiet_mode = True
                await self.db.update_agent_state(agent_state)
                found = await run_hunt_cycle(self, chat_id)
                agent_state.quiet_mode = saved_quiet
                await self.db.update_agent_state(agent_state)
                if found and self.bot:
                    await self.bot.send_message(chat_id, f"✅ <b>{found} neue Jobs</b> gefunden. /jobs für Details.")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler cycle failed")

    async def shutdown(self) -> None:
        if self.api_client:
            await self.api_client.close()
        if self.db:
            await self.db.close()
        if self.bot:
            await self.bot.session.close()
        logger.info("🛑 AppState shut down")


# ── Hunt Cycle (einmalig, vom Scheduler oder Startup aufgerufen) ────

async def run_hunt_cycle(state: AppState, chat_id: int) -> int:
    """Führt einen kompletten Hunt-Cycle aus: scrapen → evaluieren → vorschlagen.
    Returns: Anzahl gefundener Jobs."""
    logger.info("🔍 Starting hunt cycle...")
    try:
        agent_state = await state.db.get_agent_state()

        # Progress callback – sendet Status an Telegram
        async def _progress(msg: str) -> None:
            if state.bot and chat_id:
                try:
                    await state.bot.send_message(chat_id=chat_id, text=msg)
                except Exception:
                    pass

        if not agent_state.quiet_mode:
            await _progress("🔍 <b>Job-Suche gestartet...</b>")

        raw_jobs = await state.scraper.fetch_jobs(on_progress=_progress if not agent_state.quiet_mode else None)
        logger.info(f"   Found {len(raw_jobs)} raw jobs after filtering")

        if not raw_jobs:
            if not agent_state.quiet_mode:
                await _progress("❌ Keine neuen Jobs gefunden.")
            return 0

        if not agent_state.quiet_mode:
            await _progress(f"📊 <b>{len(raw_jobs)} Jobs</b> gefunden. Evaluierung gestartet...")

        rejected = await state.db.get_recent_rejected(limit=5)
        from src.agent.schemas import ProfileSummary
        profile = ProfileSummary(
            name="Daniel Peters",
            title="UX/UI Designer & AI Product Specialist",
            skills=["Figma", "UX Design", "User Research", "Prototyping", "Design Systems", "Python", "FastAPI", "Scrum", "n8n", "Synera", "LLM", "ComfyUI"],
            experience_years=9,
        )
        voice_samples = _load_voice_samples(state.config["profile"]["voice_samples_dir"])
        cv_dir = Path(state.config["cv"]["variants_dir"])
        cv_variants = [f.name for f in cv_dir.glob("*.tex")] if cv_dir.exists() else []

        found = 0
        for i, job in enumerate(raw_jobs):
            try:
                existing_job = await state.db.get_job(job.id)
                if existing_job:
                    logger.debug(f"   ⏭️ Skipped (already in DB): {job.title}")
                    continue

                if not agent_state.quiet_mode and (i + 1) % 3 == 0:
                    await _progress(f"🔎 Evaluiere {i+1}/{len(raw_jobs)}: {job.title[:40]}...")

                lang = _detect_language(job.description)
                logger.debug(f"   🔍 Evaluating {job.title} @ {job.company}...")
                evaluation = await state.api_client.evaluate(
                    job=job, rejected=rejected, profile=profile,
                    cv_variants=cv_variants, voice_samples=voice_samples, language=lang,
                )

                agent_state.total_api_calls_this_month += 1
                await state.db.update_agent_state(agent_state)

                if evaluation.score >= state.config["thresholds"]["min_score"]:
                    logger.info(f"   📊 {job.title} @ {job.company} (Score: {evaluation.score}) – processing...")
                    selected_bullets = state.bullet_selector.select(
                        job_title=job.title, job_description=job.description,
                        max_bullets=12, min_bullets=8,
                    )

                    stored = StoredJob(
                        id=job.id, title=job.title, company=job.company,
                        url=str(job.url), source=job.source, score=evaluation.score,
                        location=job.location, description=job.description[:500],
                        salary_range=job.salary_range,
                        cv_variant=evaluation.selected_cv_variant or "general",
                    )
                    await state.db.store_job(stored)

                    hunt._job_cache[job.id] = {
                        "job": job, "evaluation": evaluation, "bullets": selected_bullets, "lang": lang,
                    }

                    if not agent_state.quiet_mode:
                        bullet_lines = "\n".join(f"  • {b[:90]}" for b in selected_bullets[:4])
                        msg = (
                            f"🎯 <b>{job.title}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🏢 {job.company} | 📍 {job.location}\n"
                            f"⭐ Score: <b>{evaluation.score:.1f}/10</b>\n"
                            f"🌐 {lang.upper()} | 📡 {job.source.value}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📝 <i>{job.description[:200].replace(chr(10), ' ')}...</i>\n\n"
                            f"<b>📋 Top Bullets:</b>\n{bullet_lines}"
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="📄 CV erstellen", callback_data=f"gen_cv:{job.id}"),
                                InlineKeyboardButton(text="📝 Anschreiben", callback_data=f"gen_cl:{job.id}"),
                            ],
                            [
                                InlineKeyboardButton(text="📖 Details", callback_data=f"details:{job.id}"),
                                InlineKeyboardButton(text="🔗 Zum Portal", url=str(job.url)),
                            ],
                            [
                                InlineKeyboardButton(text="✅ Abgeschickt", callback_data=f"applied:{job.id}"),
                                InlineKeyboardButton(text="❌ Ablehnen", callback_data=f"reject:{job.id}"),
                            ],
                            [
                                InlineKeyboardButton(text="⏸️ Später", callback_data=f"later:{job.id}"),
                            ],
                        ])
                        await state.bot.send_message(
                            chat_id=chat_id, text=msg, reply_markup=kb,
                            disable_web_page_preview=True,
                        )

                    await state.db.log_event(AuditLogEntry(
                        event_type="job_proposed", job_id=job.id,
                        details=f"Score: {evaluation.score}, CV: {evaluation.selected_cv_variant}",
                    ))
                    found += 1
                    logger.info(f"   ✅ {job.title} @ {job.company} (Score: {evaluation.score})")

                    if evaluation.score > state.config["thresholds"]["top_job_score"] and evaluation.profile_tip:
                        if not agent_state.quiet_mode and chat_id:
                            await state.bot.send_message(
                                chat_id=chat_id,
                                text=f"💡 <b>Profil-Tipp:</b>\n{evaluation.profile_tip}",
                            )
                else:
                    logger.debug(f"   ⏭️ Skipped {job.title} (Score: {evaluation.score})")

            except Exception as e:
                logger.warning(f"   ⚠️ Failed to process job {job.title}: {e}")
                await state.db.log_error(
                    component="hunt_cycle", error_type="job_processing",
                    message=str(e), job_id=job.id,
                )

        deleted = await state.db.delete_old_unsent_jobs(
            retention_days=state.config["storage"]["pdf_retention_days"]
        )
        if deleted:
            logger.info(f"   🗑 Cleaned up {deleted} old unsent jobs")

        if not agent_state.quiet_mode:
            await _progress(f"✅ <b>Suche abgeschlossen:</b> {found} Jobs gefunden & gesendet.")

        return found

    except Exception:
        logger.exception("Hunt cycle failed")
        return 0

    if not config["active_hours"]["enabled"]:
        return True

    day_name = now.strftime("%a").lower()
    hours = config["active_hours"]["days"].get(day_name, [])

    if not hours:
        return False

    current_time = now.strftime("%H:%M")
    start, end = hours[0], hours[1]
    return start <= current_time <= end


def _load_profile_from_markdown(path: str) -> "ProfileSummary":
    """Lädt und parsed die master_profile.md (vereinfacht)."""
    from src.agent.schemas import ProfileSummary

    md_path = Path(path)
    if not md_path.exists():
        logger.warning(f"Profile not found at {path}, using defaults")
        return ProfileSummary(
            name="Daniel Peters",
            title="UX/UI Designer",
            skills=["Figma", "UX Design", "UI Design"],
            experience_years=9,
        )

    content = md_path.read_text(encoding="utf-8")

    # Heuristisches Parsing
    name = "Daniel Peters"
    title = "UX/UI Designer"
    skills = []

    # Name aus erstem Header
    for line in content.split("\n"):
        if line.startswith("# ") and "Daniel" in line:
            name = line.replace("# ", "").strip()
        if "**" in line and "Designer" in line:
            title = line.replace("**", "").strip()

    # Skills aus Skills-Sektion
    in_skills = False
    for line in content.split("\n"):
        if "### Skills" in line or "## Skills" in line:
            in_skills = True
            continue
        if in_skills and line.startswith("## "):
            break
        if in_skills and line.startswith("- "):
            skill = line.replace("- ", "").split(":")[0].strip()
            if skill:
                skills.append(skill)

    return ProfileSummary(
        name=name,
        title=title,
        skills=skills[:20] or ["Figma", "UX Design", "UI Design"],
        experience_years=9,
        raw_profile_md=content,
    )


def _load_voice_samples(samples_dir: str) -> list[str]:
    """Lädt Anschreiben-Samples als Voice Reference."""
    samples = []
    dir_path = Path(samples_dir)
    if dir_path.exists():
        for tex_file in dir_path.glob("*.tex"):
            content = tex_file.read_text(encoding="utf-8")
            # Extract cover letter body from LaTeX
            if "Liebe" in content or "Sehr geehrte" in content:
                # Try to extract between begin{document} and end{document}
                start = content.find("\\begin{document}")
                end = content.find("\\end{document}")
                if start > 0 and end > start:
                    body = content[start:end]
                    samples.append(body[:2000])
                else:
                    # Plain text without LaTeX wrappers
                    samples.append(content[:2000])
    return samples


def _detect_language(text: str) -> str:
    """Heuristische Spracherkennung."""
    text_lower = text.lower()
    german_indicators = ["der", "die", "das", "und", "für", "mit", "bei", "von"]
    english_indicators = ["the", "and", "for", "with", "at", "from", "you", "we"]

    german_score = sum(1 for w in german_indicators if f" {w} " in f" {text_lower} ")
    english_score = sum(1 for w in english_indicators if f" {w} " in f" {text_lower} ")

    return "de" if german_score > english_score else "en"


# ── Lifespan Manager ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(state: AppState):
    await state.initialize()
    try:
        yield
    finally:
        await state.shutdown()


# ── Main Entry Point ──────────────────────────────────────────────

async def main() -> None:
    config = load_config()
    state = AppState(config)

    async with lifespan(state):
        scheduler_task = asyncio.create_task(state._scheduler_loop(), name="hunt-scheduler")

        logger.info("🚀 Job Hunter Agent started")
        logger.info("   Scheduler: ✅ aktiv (asyncio loop)")
        logger.info("   Press Ctrl+C to stop")

        await set_bot_commands(state.bot)

        try:
            await state.dispatcher.start_polling(state.bot)
        finally:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Goodbye.")
        sys.exit(0)
