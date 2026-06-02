"""src/telegram/formatters.py – Markdown-Tabellen für KPIs."""

from __future__ import annotations

import re

from src.agent.schemas import WeeklyKPI


def latex_escape(text: str) -> str:
    """Escaped LaTeX-Sonderzeichen in einem Text (idempotent)."""
    replacements = [
        (re.compile(r"(?<!\\)&"), r"\&"),
        (re.compile(r"(?<!\\)%"), r"\%"),
        (re.compile(r"(?<!\\)\$"), r"\$"),
        (re.compile(r"(?<!\\)#"), r"\#"),
        (re.compile(r"(?<!\\)_"), r"\_"),
        (re.compile(r"(?<!\\){"), r"\{"),
        (re.compile(r"(?<!\\)}"), r"\}"),
    ]
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)
    return text


def format_briefing(kpi: WeeklyKPI) -> str:
    """Formatiert das Sunday Briefing als Markdown-Nachricht."""

    header = (
        f"📊 *Sunday Briefing*\n"
        f"Woche: {kpi.week_start.strftime('%d.%m')} – {kpi.week_end.strftime('%d.%m.%Y')}\n"
        f"{'─' * 30}\n"
    )

    stats = (
        f"\n📈 *Statistiken*\n"
        f"```\n"
        f"Jobs gescannt:        {kpi.jobs_scanned:>4}\n"
        f"Vorschläge gesendet:  {kpi.proposals_sent:>4}\n"
        f"Bewerbungen raus:     {kpi.applications_sent:>4}\n"
        f"Rejects:              {kpi.rejects:>4}\n"
        f"Akzeptiert:           {kpi.accepted:>4}\n"
        f"Ø Score:              {kpi.avg_score:>4.1f}\n"
        f"```"
    )

    trends = ""
    if kpi.top_trends:
        trends = (
            f"\n🔝 *Top Trends*\n"
            + "\n".join(f"• {trend}" for trend in kpi.top_trends[:5])
            + "\n"
        )

    tips = ""
    if kpi.profile_tips_generated > 0:
        tips = (
            f"\n💡 *Profil-Tipps generiert: {kpi.profile_tips_generated}*\n"
        )

    top_jobs = ""
    if kpi.top_jobs:
        top_jobs = (
            f"\n🎯 *Top Jobs der Woche*\n"
            + "\n".join(
                f"{i+1}. {job.get('title', '?')} @ {job.get('company', '?')} (Score: {job.get('score', 0)})"
                for i, job in enumerate(kpi.top_jobs[:3])
            )
        )

    return header + stats + trends + tips + top_jobs


def format_job_proposal(
    job: "JobListing",
    score: float,
    bullets: list[str],
) -> str:
    """Formatiert Job-Vorschlag für Telegram."""
    return (
        f"<b>{job.title}</b> @ {job.company}\n"
        f"📍 {job.location}\n"
        f"⭐ Score: <b>{score:.1f}/10</b>\n\n"
        f"<b>Top Bullets:</b>\n"
        + "\n".join(f"• {b[:100]}..." for b in bullets[:4])
    )


def format_status(state: dict) -> str:
    """Formatiert den Agent-Status."""
    status = "⏸️ Pausiert" if state.get("paused") else "▶️ Aktiv"
    quiet = "🔕 Quiet" if state.get("quiet_mode") else "🔔 Normal"

    return (
        f"*Agent Status*\n"
        f"{'─' * 20}\n"
        f"Status: {status}\n"
        f"Modus: {quiet}\n"
        f"API Calls (Monat): {state.get('total_api_calls_this_month', 0)}\n"
        f"Budget erreicht: {'Ja' if state.get('api_budget_reached') else 'Nein'}\n"
    )
