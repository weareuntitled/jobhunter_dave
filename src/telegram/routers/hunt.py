"""src/telegram/routers/hunt.py – /start, /hunt, /jobs, /stats Commands."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import F

from src.agent.schemas import (
    ApplicationStatus,
    AuditLogEntry,
    FeedbackEntry,
    JobSource,
    StoredJob,
)
from src.telegram.formatters import format_job_proposal
from src.telegram.keyboards import job_proposal_keyboard

logger = logging.getLogger("job-hunter")
router = Router()

# In-Memory Cache für Job-Daten (für Button-Handler)
_job_cache: dict = {}
_edit_mode: dict = {}  # job_id → waiting for prompt
_flow_cache: dict = {}  # job_id → message_id der Flow-Karte

FLOW_STEPS = [
    "📄 CV erstellt",
    "📝 Anschreiben erstellt",
    "✅ Abgeschickt",
]


def _render_flow_card(job, flow_step: int) -> str:
    lines = []
    for i, label in enumerate(FLOW_STEPS):
        done = flow_step > i
        icon = "✅" if done else "⬜"
        lines.append(f"{icon} <b>{label}</b>")
    return (
        f"📋 <b>Bewerbungsstatus</b>\n"
        f"{'━' * 25}\n"
        f"🎯 <b>{job.title}</b> @ {job.company}\n"
        f"{'━' * 25}\n"
        + "\n".join(lines)
    )


def _flow_keyboard(job_id: str, flow_step: int) -> InlineKeyboardMarkup:
    buttons = []
    if flow_step < 3:
        next_label = FLOW_STEPS[flow_step]
        buttons.append([
            InlineKeyboardButton(text=f"▶️ {next_label}", callback_data=f"flow_next:{job_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_or_update_flow_card(callback: CallbackQuery, job_id: str) -> int:
    """Sendet Flow-Karte oder updated existierende. Returns message_id."""
    cached = _job_cache.get(job_id)
    if not cached:
        return 0
    job = cached["job"]
    flow_step = cached.get("flow_step", 0)
    text = _render_flow_card(job, flow_step)
    kb = _flow_keyboard(job_id, flow_step)

    existing = _flow_cache.get(job_id)
    if existing:
        try:
            msg = await callback.bot.edit_message_text(
                text=text, chat_id=callback.message.chat.id,
                message_id=existing, reply_markup=kb,
            )
            return msg.message_id
        except Exception:
            pass  # Neu senden wenn edit fehlschlägt

    msg = await callback.message.answer(text=text, reply_markup=kb)
    _flow_cache[job_id] = msg.message_id
    return msg.message_id


# ── /start – Welcome + Quick-Action Keyboard ───────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, db) -> None:
    """Willkommens-Nachricht mit Quick-Action Buttons + Job-Count."""
    # Job-Count laden (Phase 6, Feature 29)
    async with db.db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'pending'") as c:
        pending_count = (await c.fetchone())[0] or 0
    async with db.db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'sent'") as c:
        sent_count = (await c.fetchone())[0] or 0
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Jetzt Jobs suchen", callback_data="quick_hunt")],
        [
            InlineKeyboardButton(text="📋 Meine Jobs", callback_data="quick_jobs"),
            InlineKeyboardButton(text="📊 Statistiken", callback_data="quick_stats"),
        ],
        [
            InlineKeyboardButton(text="⏸️ Pausieren", callback_data="quick_pause"),
            InlineKeyboardButton(text="▶️ Fortsetzen", callback_data="quick_resume"),
        ],
    ])
    await message.answer(
        "🤖 <b>Job Hunter Agent</b>\n\n"
        "Ich suche automatisch nach UX/UI und Product Designer Jobs und schlage dir die besten vor.\n\n"
        f"<b>📊 Status:</b>\n"
        f"🟡 {pending_count} offene Jobs\n"
        f"🟢 {sent_count} abgeschickt\n\n"
        "<b>Quick Actions:</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data == "quick_hunt")
async def cb_quick_hunt(callback: CallbackQuery, db, app) -> None:
    """Quick-Hunt via Button."""
    await callback.answer("🔍 Suche gestartet...")
    await cmd_hunt_from(callback.message, db, app)


@router.callback_query(F.data == "quick_jobs")
async def cb_quick_jobs(callback: CallbackQuery, db) -> None:
    """Quick-Jobs via Button."""
    await callback.answer("📋 Lade Jobs...")
    await cmd_jobs_from(callback.message, db)


@router.callback_query(F.data == "quick_stats")
async def cb_quick_stats(callback: CallbackQuery, db) -> None:
    """Quick-Stats via Button."""
    await callback.answer("📊 Lade Statistiken...")
    await cmd_stats_from(callback.message, db)


@router.callback_query(F.data == "quick_pause")
async def cb_quick_pause(callback: CallbackQuery, db) -> None:
    from src.agent.schemas import AgentState
    state = await db.get_agent_state()
    state.paused = True
    await db.update_agent_state(state)
    await callback.message.answer("⏸️ Agent pausiert.")
    await callback.answer()


@router.callback_query(F.data == "quick_resume")
async def cb_quick_resume(callback: CallbackQuery, db) -> None:
    from src.agent.schemas import AgentState
    state = await db.get_agent_state()
    state.paused = False
    await db.update_agent_state(state)
    await callback.message.answer("▶️ Agent aktiv.")
    await callback.answer()


# ── /hunt – Manueller Hunt-Cycle ──────────────────────────────────

KEYWORD_CATEGORIES = {
    "🎨 UX/UI Design": [
        "UX Designer", "UI Designer", "UX/UI Designer", "Product Designer",
        "Digital Product Designer", "Senior UX Designer", "Senior Product Designer",
        "Interaction Designer", "Experience Designer", "Visual Designer",
        "UX Architect", "Service Designer", "UX Researcher", "Design Systems",
    ],
    "🎬 Motion & Multimedia": [
        "Motion Designer", "Motion Graphics Designer", "Multimedia Designer",
        "Digital Creator", "Creative Technologist",
    ],
    "📋 Product & Agile": [
        "Product Owner", "Scrum Master", "Agile Coach", "Product Manager",
        "Digital Product Manager", "Technical Product Owner",
        "Digital Transformation Manager", "Innovation Manager",
        "Agile Project Manager", "Delivery Lead",
    ],
    "🤖 AI & KI": [
        "Artificial Intelligence", "Machine Learning", "LLM",
        "Prompt Engineer", "AI Engineer", "KI Engineer", "AI Developer",
        "AI Product", "KI-Assistent", "AI Automation Specialist",
        "Workflow Automation", "Process Automation Engineer",
        "Business Automation", "Low-Code", "No-Code",
        "AI Consultant", "KI Berater", "Conversational AI Designer",
        "Generative AI",
    ],
}

# Callback-data → Keyword Mapping (for toggle buttons)
_keyword_selection: dict[str, set[str]] = {}  # chat_id → selected keywords


def _keyword_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    """Baut Inline-Keyboard für Keyword-Auswahl."""
    buttons = []

    # Kategorie-Buttons (alle an/aus)
    for cat_name, kws in KEYWORD_CATEGORIES.items():
        all_selected = all(kw in selected for kw in kws)
        icon = "✅" if all_selected else "⬜"
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {cat_name}",
                callback_data=f"kw_cat:{cat_name}",
            )
        ])

    # Individuelle Keywords (je 2 pro Zeile)
    for cat_name, kws in KEYWORD_CATEGORIES.items():
        for i in range(0, len(kws), 2):
            row = []
            for kw in kws[i:i+2]:
                icon = "✅" if kw in selected else "⬜"
                row.append(InlineKeyboardButton(
                    text=f"{icon} {kw}",
                    callback_data=f"kw_toggle:{kw}",
                ))
            buttons.append(row)

    # Start-Button
    buttons.append([
        InlineKeyboardButton(
            text=f"🔍 Hunt starten ({len(selected)} Keywords)",
            callback_data="kw_start_hunt",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("hunt"))
async def cmd_hunt(message: Message, db, app) -> None:
    """Zeigt Keyword-Auswahl vor dem Hunt."""
    chat_id = str(message.chat.id)

    # Default: alle Keywords ausgewählt
    all_kws = set()
    for kws in KEYWORD_CATEGORIES.values():
        all_kws.update(kws)
    _keyword_selection[chat_id] = all_kws.copy()

    await message.answer(
        "🔍 <b>Keyword-Auswahl für Job-Suche</b>\n\n"
        "Wähle Keywords aus oder starte direkt mit Allen:",
        reply_markup=_keyword_keyboard(all_kws),
    )


@router.callback_query(F.data.startswith("kw_toggle:"))
async def cb_kw_toggle(callback: CallbackQuery) -> None:
    """Einzelnes Keyword togglen."""
    kw = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)

    if chat_id not in _keyword_selection:
        _keyword_selection[chat_id] = set()

    if kw in _keyword_selection[chat_id]:
        _keyword_selection[chat_id].remove(kw)
    else:
        _keyword_selection[chat_id].add(kw)

    await callback.message.edit_reply_markup(
        reply_markup=_keyword_keyboard(_keyword_selection[chat_id])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("kw_cat:"))
async def cb_kw_category(callback: CallbackQuery) -> None:
    """Alle Keywords einer Kategorie togglen."""
    cat_name = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)

    if chat_id not in _keyword_selection:
        _keyword_selection[chat_id] = set()

    kws = KEYWORD_CATEGORIES.get(cat_name, [])
    all_selected = all(kw in _keyword_selection[chat_id] for kw in kws)

    if all_selected:
        # Alle abwählen
        for kw in kws:
            _keyword_selection[chat_id].discard(kw)
    else:
        # Alle auswählen
        _keyword_selection[chat_id].update(kws)

    await callback.message.edit_reply_markup(
        reply_markup=_keyword_keyboard(_keyword_selection[chat_id])
    )
    await callback.answer()


@router.callback_query(F.data == "kw_start_hunt")
async def cb_kw_start_hunt(callback: CallbackQuery, db, app) -> None:
    """Hunt mit ausgewählten Keywords starten."""
    chat_id = str(callback.message.chat.id)
    selected = _keyword_selection.get(chat_id, set())

    if not selected:
        await callback.answer("❌ Keine Keywords ausgewählt!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"🔍 Starte mit {len(selected)} Keywords...")

    # Temporär: Keywords in Config überschreiben
    original_keywords = app.config["search"]["keywords"].copy()
    app.config["search"]["keywords"] = list(selected)

    try:
        await cmd_hunt_from(callback.message, db, app)
    finally:
        # Keywords wiederherstellen
        app.config["search"]["keywords"] = original_keywords


async def cmd_hunt_from(message: Message, db, app) -> None:
    """Startet einen manuellen Hunt-Cycle: Scraping → Evaluate → Bullets → Telegram."""
    await message.answer("🔍 <b>Starte Job-Suche...</b>")

    try:
        # Profile laden
        from pathlib import Path
        profile_md = str(Path(app.config["profile"]["master_path"]).read_text())[:3000]
    except Exception:
        profile_md = "UX Designer mit M.Sc. und 5 Jahren Erfahrung."

    from src.agent.schemas import ProfileSummary
    profile = ProfileSummary(name="Daniel Peters", title="UX/UI Designer & AI Product Specialist", skills=["Figma","UX Design","User Research","Prototyping","Design Systems","Python","FastAPI","Scrum","n8n","Synera","LLM","ComfyUI"], experience_years=9)

    # Scraping
    raw_jobs = await app.scraper.fetch_jobs()
    await message.answer(f"📋 <b>{len(raw_jobs)} Jobs gefunden.</b> Evaluiere...")

    found = 0
    for job in raw_jobs[:8]:  # Max 8 pro Hunt
        try:
            existing_job = await db.get_job(job.id)
            if existing_job and existing_job.status in [ApplicationStatus.SENT, ApplicationStatus.REJECTED, ApplicationStatus.SKIPPED]:
                continue

            # Sprache
            lang = "de"
            if sum(1 for w in ["the","and","for","you","we"] if w in job.description.lower().split()) > 2:
                lang = "en"

            # Evaluate
            evaluation = await app.api_client.evaluate(
                job=job, rejected=[], profile=profile,
                cv_variants=["general.tex"], voice_samples=[], language=lang,
            )

            # Score prüfen
            if evaluation.score < app.config["thresholds"]["min_score"]:
                continue

            # Bullets
            bullets = app.bullet_selector.select(job.title, job.description, max_bullets=6)

            # In DB speichern
            stored = StoredJob(
                id=job.id, title=job.title, company=job.company,
                url=str(job.url), source=job.source, score=evaluation.score,
                location=job.location, description=job.description[:500],
                salary_range=getattr(job, 'salary_range', None),
                cv_variant=evaluation.selected_cv_variant or "general",
            )
            await db.store_job(stored)

            # Im Cache für Button-Handler speichern
            _job_cache[job.id] = {
                "job": job, "evaluation": evaluation, "bullets": bullets, "lang": lang,
            }

            # Telegram-Nachricht
            bullet_lines = "\n".join(f"  • {b[:90]}" for b in bullets[:4])
            salary_str = f"\n💰 {job.salary_range}" if job.salary_range else ""
            msg = (
                f"🎯 <b>{job.title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏢 {job.company} | 📍 {job.location}{salary_str}\n"
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

            await message.answer(msg, reply_markup=kb, disable_web_page_preview=True)
            found += 1
            await db.log_event(AuditLogEntry(event_type="job_proposed", job_id=job.id, details=f"Score: {evaluation.score}"))

        except Exception as e:
            logger.warning(f"Hunt: Failed {job.title}: {e}")

    if found == 0:
        await message.answer("😕 <b>Keine passenden Jobs gefunden.</b> Versuch andere Keywords.")
    else:
        await message.answer(f"✅ <b>{found} Jobs vorgeschlagen.</b>")


# ── Multi-Step Apply Flow ──────────────────────────────────────────

@router.callback_query(F.data.startswith("applied:"))
async def handle_applied(callback: CallbackQuery, db) -> None:
    """User hat sich beworben → als 'sent' markieren + Flow-Karte updaten."""
    job_id = callback.data.split(":")[1]
    await db.update_job_status(job_id, ApplicationStatus.SENT)

    cached = _job_cache.get(job_id)
    if cached:
        cached["flow_step"] = max(cached.get("flow_step", 0), 3)
        await _send_or_update_flow_card(callback, job_id)

    await callback.answer("✅ Gespeichert")


@router.callback_query(F.data.startswith("reject:"))
async def handle_reject(callback: CallbackQuery, db) -> None:
    """User lehnt Job ab → REJECTED."""
    job_id = callback.data.split(":")[1]
    await db.update_job_status(job_id, ApplicationStatus.REJECTED)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer("❌ Abgelehnt")


@router.callback_query(F.data.startswith("flow_next:"))
async def handle_flow_next(callback: CallbackQuery, app, db) -> None:
    """'▶️ Nächster Schritt' Button auf der Flow-Karte."""
    job_id = callback.data.split(":")[1]
    cached = _job_cache.get(job_id)
    if not cached:
        await callback.answer("⚠️ Daten nicht mehr im Cache.")
        return

    flow_step = cached.get("flow_step", 0)
    job = cached["job"]

    if flow_step == 0:
        # Schritt 1: CV erstellen
        await handle_gen_cv(callback, app)
    elif flow_step == 1:
        # Schritt 2: Anschreiben erstellen
        await handle_gen_cl(callback, app)
    elif flow_step == 2:
        # Schritt 3: Abgeschickt markieren
        await db.update_job_status(job_id, ApplicationStatus.SENT)
        cached["flow_step"] = 3
        await _send_or_update_flow_card(callback, job_id)
        await callback.answer("✅ Als abgeschickt markiert")
    else:
        await callback.answer("✅ Bereits erledigt")


@router.callback_query(F.data.startswith("later:"))
async def handle_later(callback: CallbackQuery) -> None:
    """Job für später speichern."""
    await callback.message.edit_text(
        text=callback.message.text + "\n\n⏸️ <b>Gespeichert für später.</b>",
        reply_markup=None,
    )
    await callback.answer("⏸️ Gespeichert")


@router.callback_query(F.data.startswith("details:"))
async def handle_details(callback: CallbackQuery) -> None:
    """Zeigt vollständige Job-Beschreibung (Phase 6, Feature 30)."""
    job_id = callback.data.split(":")[1]
    cached = _job_cache.get(job_id)
    if not cached:
        await callback.answer("⚠️ Daten nicht mehr im Cache. Bitte /hunt neu starten.")
        return
    
    job = cached["job"]
    # Sende vollständige Beschreibung als separate Nachricht
    await callback.message.answer(
        f"📖 <b>Vollständige Beschreibung:</b>\n\n"
        f"<b>{job.title}</b> @ {job.company}\n"
        f"📍 {job.location}\n\n"
        f"{job.description[:2000]}"
    )
    await callback.answer("📖 Details gesendet")


# ── /jobs – Job-Historie ───────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message) -> None:
    """Löscht alle gecachten Job-Daten."""
    count = len(_job_cache)
    _job_cache.clear()
    _edit_mode.clear()
    await message.answer(f"🧹 <b>{count} Jobs aus Cache gelöscht.</b> /hunt für neue Suche.")


# ── PDF Generierung per Button ─────────────────────────────────────

@router.callback_query(F.data.startswith("gen_cv:"))
async def handle_gen_cv(callback: CallbackQuery, app) -> None:
    """'CV erstellen' Button → CV-PDF kompilieren & senden."""
    job_id = callback.data.split(":")[1]
    cached = _job_cache.get(job_id)
    if not cached:
        await callback.answer("⚠️ Daten nicht mehr im Cache. Bitte /hunt neu starten.")
        return

    await callback.answer("📄 Kompiliere CV...")
    job = cached["job"]
    bullets = cached["bullets"]
    lang = cached["lang"]

    try:
        # CV-Template rendern
        from jinja2 import Environment
        from src.telegram.formatters import latex_escape
        escaped_bullets = [latex_escape(b) for b in bullets]

        latex_env = Environment(block_start_string="<%", block_end_string="%>", variable_start_string="<<", variable_end_string=">>")
        cv_template = latex_env.from_string(Path("data/cv/general.tex").read_text(encoding="utf-8"))

        # Bullets per Employer splitten
        bullets_8020, bullets_untitled = app.bullet_selector.split_by_employer(
            job.title, job.description, max_bullets=12, min_bullets=8,
        )
        escaped_8020 = [latex_escape(b) for b in bullets_8020]
        escaped_untitled = [latex_escape(b) for b in bullets_untitled]

        # 8020 Section
        exp_8020 = (
            "\\textbf{8020 GmbH Management Consulting, Ingolstadt}\\par\n"
            "\\textbf{Management Consultant, Product Designer, Scrum Master}\\par\n"
            "\\textit{Jul 2022 bis Okt 2025}\\par\n"
            "\\vspace{4pt}\n"
            "\\begin{itemize}\n"
            + ("\n".join(f"    \\item {b}" for b in escaped_8020) if escaped_8020
               else "    \\item Product Ownership und Scrum Master für Enterprise-Projekte (Audi, Porsche, VW)")
            + "\n\\end{itemize}\n"
            "\\textbf{Kunden:} Audi \\textbullet\\ Porsche \\textbullet\\ Volkswagen \\textbullet\\ MAN \\textbullet\\ Centus\\par\n"
            "\\vspace{12pt}\n"
        )

        # UNTITLED UX Section
        bot_bullet = "JobHunter Dave Bot entwickelt und betrieben -- autonomer KI-Bewerbungs-Agent für Job-Suche, CV-Generierung und Bewerbungs-Automation (Python, aiogram, FastAPI, LLMs)."
        untitled_bullets = [bot_bullet] + (escaped_untitled if escaped_untitled else [
            "UX/UI Design, Webentwicklung und AI-gestützte Workflows für verschiedene Kunden."
        ])
        exp_untitled = (
            "\\textbf{UNTITLED UX, Augsburg}\\par\n"
            "\\textbf{Freelance UX/UI Designer \\& Full-Stack Developer}\\par\n"
            "\\textit{Feb 2020 bis heute}\\par\n"
            "\\vspace{4pt}\n"
            "\\begin{itemize}\n"
            + "\n".join(f"    \\item {b}" for b in untitled_bullets)
            + "\n\\end{itemize}\n"
        )
        exp_smartpatient = (
            "\\vspace{8pt}\n"
            "\\textbf{smartpatient GmbH, München}\\par\n"
            "\\textbf{UX Design und Research Praktikum}\\par\n"
            "\\textit{Aug 2016 bis Jan 2017}\\par\n"
            "\\vspace{4pt}\n"
            "\\begin{itemize}\n"
            "    \\item Nutzerfeedback und Support-Tickets in UX-Anforderungen und Screenkonzepte übersetzt.\n"
            "    \\item Usability-Tests mitgeplant, durchgeführt und ausgewertet.\n"
            "\\end{itemize}"
        )
        kontrast = (
            "\\textbf{Kontrast Festival GbR, Augsburg}\\par\n"
            "\\textbf{Co-Founder \\& Design Lead}\\par\n"
            "\\textit{2021 bis 2024}\\par\n"
            "\\vspace{4pt}\n"
            "\\begin{itemize}\n"
            "    \\item Aufbau einer Kulturmarke mit über 4.000 Besucher:innen und rund 200.000 EUR Jahresumsatz.\n"
            "    \\item Visuelle Identität verantwortet und Kreativteam von 5--7 Personen geführt.\n"
            "\\end{itemize}\n"
            "\\vspace{6pt}\n"
            "\\textbf{Dialog Act Classification (THI \\& BSH), Ingolstadt}\\par\n"
            "\\textbf{Projektleitung Studierendenteam}\\par\n"
            "\\textit{2020 bis 2021}\\par\n"
            "\\vspace{4pt}\n"
            "\\begin{itemize}\n"
            "    \\item Leitung eines interdisziplinären Teams von ~20 Studierenden.\n"
            "    \\item Mitwirkung an Publikation auf der ICNLSP 2021.\n"
            "\\end{itemize}"
        )

        static_skills = [latex_escape(s) for s in app.config["cv"].get("static_skills", [])]

        ctx = {
            "name": "Daniel Peters", "title": latex_escape("UX/UI Designer & AI Product Specialist"),
            "location": "Augsburg, Germany", "email": "hi@untitled-ux.de",
            "phone": "+49 173 5231109", "portfolio_url": "portfolio.untitled-ux.de",
            "photo_path": "photo.jpg", "date": datetime.now().strftime("%d.%m.%Y"),
            "experience": exp_8020 + exp_untitled + exp_smartpatient,
            "skills": static_skills,
            "static_skills": static_skills,
            "skills_text": " \\textbullet\\ ".join(static_skills),
            "education": "\\textbf{TH Ingolstadt} \\hfill Ingolstadt, Deutschland\\\\\nM.Sc. User Experience Design, Note 1,3 \\hfill 2021 bis 2024\\\\[2pt]\n\\textbf{TH Ingolstadt} \\hfill Ingolstadt, Deutschland\\\\\nB.Sc. User Experience Design \\hfill Okt 2014 bis März 2019",
            "leadership": kontrast,
            "languages": "Deutsch (Muttersprache), Englisch (C1), Chinesisch (B1)",
        }

        tex = cv_template.render(ctx)
        import shutil
        import tempfile
        import asyncio
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Photo ins tmpdir kopieren (relativer Pfad im Template, Tectonic läuft in tmpdir)
            photo_src = Path("data/photo.jpg")
            if photo_src.exists():
                shutil.copy2(photo_src, tmp / "photo.jpg")
            tex_file = tmp / "cv.tex"
            tex_file.write_text(tex, encoding="utf-8")
            # Run Tectonic async to avoid blocking
            proc = await asyncio.create_subprocess_exec(
                os.path.expanduser("~/.local/bin/tectonic"),
                str(tex_file),
                cwd=tmpdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                pdf = tmp / "cv.pdf"
                today = datetime.now().strftime("%Y-%m-%d")
                safe_company = "".join(c if c.isalnum() else "_" for c in job.company)[:20]
                cv_name = f"Daniel_Peters_CV_{safe_company}_{today}.pdf"
                from aiogram.types import FSInputFile
                await callback.message.answer_document(
                    document=FSInputFile(str(pdf), filename=cv_name),
                    caption=f"📄 <b>{job.title}</b> @ {job.company}\n<i>KI-gestütztes CV -- erstellt mit meinem eigenen Agenten</i>",
                )
                cached["flow_step"] = max(cached.get("flow_step", 0), 1)
                await _send_or_update_flow_card(callback, job_id)
                await callback.answer("✅ CV gesendet")
            else:
                raise RuntimeError(stderr.decode()[:200])
    except Exception as e:
        await callback.message.answer(f"⚠️ CV-Erstellung fehlgeschlagen: {e}")
        await callback.answer("❌ Fehler")


@router.callback_query(F.data.startswith("gen_cl:"))
async def handle_gen_cl(callback: CallbackQuery, app) -> None:
    """'Anschreiben' Button → Cover Letter via LLM generieren, PDF kompilieren & senden."""
    job_id = callback.data.split(":")[1]
    cached = _job_cache.get(job_id)
    if not cached:
        await callback.answer("⚠️ Daten nicht mehr im Cache. Bitte /hunt neu starten.")
        return

    await callback.answer("🤖 Generiere Anschreiben...")
    job = cached["job"]
    evaluation = cached["evaluation"]
    bullets = cached.get("bullets", [])
    lang = _detect_language(job.description)

    try:
        from src.agent.schemas import ProfileSummary
        profile = ProfileSummary(
            name="Daniel Peters", title="UX/UI Designer & AI Product Specialist",
            skills=["Figma", "UX Design", "User Research", "Prototyping", "Design Systems", "Python", "FastAPI", "Scrum", "n8n", "Synera", "LLM", "ComfyUI"],
            experience_years=9,
        )

        from src.agent.llm_client import generate_cover_letter
        text = await generate_cover_letter(job, profile, bullets, lang)
        if text and len(text.strip()) >= 50:
            evaluation.adapted_cover_letter = text.strip()

        profile_data = {
            "name": "Daniel Peters", "title": "UX/UI Designer & AI Product Specialist",
            "location": "Augsburg", "email": "hi@untitled-ux.de",
            "phone": "+49 173 5231109", "application_language": lang,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "salary_expectation": "", "photo_path": app.config["cv"]["photo_path"],
            "include_photo": bool(app.config["agent"].get("include_photo", False)),
        }
        pdf_path = await app.compiler.compile(evaluation=evaluation, job=job, profile_data=profile_data)

        from aiogram.types import FSInputFile
        today = datetime.now().strftime("%Y-%m-%d")
        safe_company = "".join(c if c.isalnum() else "_" for c in job.company)[:20]
        cl_name = f"Daniel_Peters_Anschreiben_{safe_company}_{today}.pdf"
        await callback.message.answer_document(
            document=FSInputFile(pdf_path, filename=cl_name),
            caption=f"📝 <b>{job.title}</b> @ {job.company}\n<i>KI-gestütztes Anschreiben -- mein eigener Agent</i>",
        )
        cached["flow_step"] = max(cached.get("flow_step", 0), 2)
        await _send_or_update_flow_card(callback, job_id)
        await callback.answer("✅ Anschreiben gesendet")
    except Exception as e:
        await callback.message.answer(f"⚠️ Anschreiben-Erstellung fehlgeschlagen: {e}")
        await callback.answer("❌ Fehler")


# ── Edit-Modus: Prompt für Anpassung ───────────────────────────────

@router.callback_query(F.data.startswith("editcv:"))
async def handle_edit_cv(callback: CallbackQuery) -> None:
    job_id = callback.data.split(":")[1]
    _edit_mode[job_id] = callback.message.chat.id
    await callback.message.answer(
        "✏️ <b>Edit-Modus aktiv</b>\n\n"
        "Schick mir deine Änderungen als Text oder Sprachnachricht.\n"
        "Beispiele:\n"
        "• \"Mehr Fokus auf AI-Kompetenz\"\n"
        "• \"Gehalt auf 65.000 erhöhen\"\n"
        "• \"Englische Version\"\n\n"
        "Zum Beenden: /clear"
    )
    await callback.answer("✏️ Edit-Modus")


@router.message(lambda m: m.text and not m.text.startswith("/"))
async def handle_edit_prompt(message: Message, app) -> None:
    """Verarbeitet Edit-Prompts, wenn ein Job im Edit-Modus ist."""
    if not _edit_mode:
        return  # Kein Edit-Modus aktiv

    chat_id = message.chat.id
    await message.answer(f"🔧 <i>Prompt empfangen: \"{message.text[:200]}\"</i>\n⏳ Generiere neue Version...")

    # TODO: Go-API mit Prompt anfragen, aktuell: einfaches Rerun
    await message.answer(
        "✅ <b>Änderungen vermerkt.</b>\n"
        "Klick erneut auf 📄 CV oder 📝 Anschreiben für die neue Version.\n\n"
        "<i>Volle Prompt-Verarbeitung via Go-API in Phase 2.</i>"
    )

@router.message(Command("jobs"))
async def cmd_jobs(message: Message, db) -> None:
    """Zeigt alle Jobs als Liste mit Buttons."""
    pending = await db.get_jobs_by_status(ApplicationStatus.PENDING, limit=50)
    sent = await db.get_jobs_by_status(ApplicationStatus.SENT, limit=50)
    rejected = await db.get_jobs_by_status(ApplicationStatus.REJECTED, limit=50)

    if not pending and not sent and not rejected:
        await message.answer("_Noch keine Jobs. Nutze /hunt zum Suchen._")
        return

    for label, jobs, emoji in [
        ("🟡 Offen", pending, "🟡"),
        ("🟢 Abgeschickt", sent, "✅"),
        ("🔴 Abgelehnt", rejected, "❌"),
    ]:
        if not jobs:
            continue
        # Batch: 5 Jobs pro Nachricht
        for i in range(0, len(jobs), 5):
            batch = jobs[i:i+5]
            lines = [f"<b>{label}</b>\n"]
            kb_buttons = []
            for j in batch:
                lines.append(f"  {emoji} <b>{j.title[:50]}</b> @ {j.company[:25]} ({j.score:.1f})")
                kb_buttons.append([
                    InlineKeyboardButton(text=f"📄 {j.title[:25]}", callback_data=f"jobcv:{j.id}"),
                    InlineKeyboardButton(text=f"📝 Anschreiben", callback_data=f"jbcl:{j.id}"),
                ])
            kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
            await message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data.startswith("jobcv:") | F.data.startswith("jbcl:"))
async def handle_job_list_apply(callback: CallbackQuery, app, db) -> None:
    """Button aus /jobs-Liste → CV oder Anschreiben generieren."""
    action, job_id = callback.data.split(":", 1)
    if job_id not in _job_cache:
        stored = await db.get_job(job_id)
        if not stored:
            await callback.answer("⚠️ Job nicht gefunden")
            return
        _job_cache[job_id] = _entry_from_stored(stored)

    if action == "jobcv":
        await handle_gen_cv(callback, app)
    else:
        await handle_gen_cl(callback, app)


def _entry_from_stored(stored: StoredJob) -> dict:
    """Rekonstruiert einen Cache-Eintrag aus einem StoredJob."""
    from src.agent.schemas import JobListing, JobSource, ProfileSummary, EvaluateResponse
    from src.agent.bullet_selector import BulletSelector
    from pydantic import HttpUrl

    url_str = stored.url if stored.url.startswith("http") else f"https://{stored.url}"
    safe_desc = stored.description or f"{stored.title} bei {stored.company}"
    job = JobListing(
        id=stored.id, title=stored.title, company=stored.company,
        location=stored.location or "Remote",
        url=HttpUrl(url_str),
        source=stored.source,
        description=safe_desc,
        salary_range=stored.salary_range,
    )
    selector = BulletSelector()
    bullets = selector.select(job.title, job.description, max_bullets=6, min_bullets=3)
    evaluation = EvaluateResponse(
        score=stored.score,
        reasoning="Aus DB rekonstruiert – kein Mock/API-Call.",
        adapted_cover_letter="ich bin der KI-Bewerbungs-Agent von Daniel Peters. Mein System hat diese Stelle analysiert und als relevant eingestuft.",
        selected_cv_variant=stored.cv_variant or "general",
    )
    lang = "de"
    if sum(1 for w in ["the", "and", "for", "you", "we"] if w in job.description.lower().split()) > 2:
        lang = "en"

    return {"job": job, "evaluation": evaluation, "bullets": bullets, "lang": lang}


# ── /stats – Echte Statistiken ─────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, db) -> None:
    """Zeigt echte Agent-Statistiken."""
    state = await db.get_agent_state()
    kpi = await db.get_weekly_kpi()
    
    total = sum(1 for _ in [])  # Count from jobs table
    async with db.db.execute("SELECT COUNT(*) FROM jobs") as c:
        total = (await c.fetchone())[0] or 0

    msg = (
        f"📊 <b>Statistiken</b>\n"
        f"{'━' * 25}\n"
        f"🔍 Jobs gescannt: <b>{total}</b>\n"
        f"📬 Abgeschickt: <b>{kpi.proposals_sent}</b>\n"
        f"❌ Abgelehnt: <b>{kpi.rejects}</b>\n"
        f"✅ Akzeptiert: <b>{kpi.accepted}</b>\n"
        f"⭐ Ø Score: <b>{kpi.avg_score:.1f}</b>\n"
        f"🤖 API Calls (Monat): <b>{state.total_api_calls_this_month}</b>\n"
        f"{'━' * 25}\n"
        f"Status: {'⏸️ Pausiert' if state.paused else '▶️ Aktiv'}\n"
        f"Modus: {'🔕 Quiet' if state.quiet_mode else '🔔 Normal'}"
    )

    await message.answer(msg)


def _detect_language(text: str) -> str:
    """Heuristische Spracherkennung für Anschreiben (Phase 6, Feature 31)."""
    text_lower = text.lower()
    german_indicators = ["der", "die", "das", "und", "für", "mit", "bei", "von", "wir", "suchen"]
    english_indicators = ["the", "and", "for", "with", "at", "from", "you", "we", "looking", "seeking"]

    german_score = sum(1 for w in german_indicators if f" {w} " in f" {text_lower} ")
    english_score = sum(1 for w in english_indicators if f" {w} " in f" {text_lower} ")

    return "de" if german_score >= english_score else "en"


# ── 🃏 Swipe-Mode (Tinder für Jobs) ──────────────────────────────

_swipe_state: dict[str, dict] = {}  # chat_id → {jobs: [...], index: int, details_cache: {}}


def _render_swipe_card(
    job, index: int, total: int, score: float,
    source: str,
) -> str:
    desc = (job.description or "")[:400].replace("\n", " ").strip()
    salary = getattr(job, 'salary_range', None)

    lines = [
        f"🃏 <b>{index}/{total}</b>",
        "",
        f"<b>{job.title}</b>",
        f"🏢 {job.company}",
        f"📍 {job.location}",
    ]

    if salary:
        lines.append(f"💰 {salary}")

    lines.append("")

    bar = "█" * int(score) + "░" * (10 - int(score))
    lines.append(f"📊 Match {bar} <b>{score:.1f}/10</b>")

    if desc:
        lines.append("")
        lines.append(f"📝 {desc}...")

    lines.append("")
    lines.append(f"📡 {source} | <a href='{job.url}'>Zum Portal</a>")

    return "\n".join(lines)


def _swipe_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Skip", callback_data=f"swipe_skip:{job_id}"),
            InlineKeyboardButton(text="✅ Merken", callback_data=f"swipe_keep:{job_id}"),
        ],
    ])


@router.message(Command("swipe"))
async def cmd_swipe(message: Message, db, app) -> None:
    """Zeigt PENDING Jobs im Tinder-Mode an."""
    chat_id = str(message.chat.id)

    pending = await db.get_jobs_by_status(ApplicationStatus.PENDING, limit=50)
    if not pending:
        await message.answer("🎉 <b>Alle Jobs durch!</b>\nKeine pending Jobs zum Swipen.")
        return

    _swipe_state[chat_id] = {
        "jobs": [j for j in pending if j.id],
        "index": 0,
        "details_cache": {},
    }

    await _show_swipe_job(message, chat_id, db)


async def _show_swipe_job(msg_or_cb, chat_id: str, db) -> None:
    state = _swipe_state.get(chat_id)
    if not state or state["index"] >= len(state["jobs"]):
        total = len(state["jobs"]) if state else 0
        text = f"🎉 <b>Alle {total} Jobs durch!</b>\n/gemerkte für deine Auswahl."
        if isinstance(msg_or_cb, CallbackQuery):
            await msg_or_cb.message.answer(text)
        else:
            await msg_or_cb.answer(text)
        return

    job = state["jobs"][state["index"]]
    idx = state["index"] + 1
    total = len(state["jobs"])

    if isinstance(msg_or_cb, CallbackQuery):
        await msg_or_cb.answer(f"🃏 {idx}/{total}")

    score = float(getattr(job, 'score', 5.0) or 5.0)
    source = getattr(job, 'source', None)
    source_str = source.value if source else "unknown"

    text = _render_swipe_card(job, idx, total, score, source_str)
    kb = _swipe_keyboard(job.id)

    if isinstance(msg_or_cb, CallbackQuery):
        await msg_or_cb.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    else:
        await msg_or_cb.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("swipe_skip:"))
async def cb_swipe_skip(callback: CallbackQuery, db, app) -> None:
    job_id = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)

    await db.update_job_status(job_id, ApplicationStatus.SKIPPED)

    state = _swipe_state.get(chat_id)
    if state:
        state["index"] += 1

    try:
        await callback.message.delete()
    except Exception:
        pass

    await _show_swipe_job(callback, chat_id, db)


@router.callback_query(F.data.startswith("swipe_keep:"))
async def cb_swipe_keep(callback: CallbackQuery, db, app) -> None:
    job_id = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)

    await db.update_job_status(job_id, ApplicationStatus.KEPT)

    state = _swipe_state.get(chat_id)
    if state:
        state["index"] += 1

    try:
        await callback.message.delete()
    except Exception:
        pass

    await _show_swipe_job(callback, chat_id, db)
