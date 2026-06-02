"""src/telegram/routers/feedback.py – Reject-Callback + Learning Loop."""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.agent.schemas import ApplicationStatus, FeedbackEntry
from src.database.queries import JobRepository
from src.telegram.keyboards import reject_reason_keyboard

logger = logging.getLogger("job-hunter")
router = Router()


@router.callback_query(F.data.startswith("reject:"))
async def handle_reject(callback: CallbackQuery, db: JobRepository) -> None:
    """Handler für [❌ Reject] Button → fragt nach Grund."""
    job_id = callback.data.split(":")[1]

    await callback.message.edit_text(
        text=f"❌ <b>Abgelehnt</b>\n\nWarum passt dieser Job nicht? (oder Skip)",
        reply_markup=reject_reason_keyboard(job_id),
    )
    await callback.answer("Grund auswählen")


@router.callback_query(F.data.startswith("reject_reason:"))
async def handle_reject_reason(callback: CallbackQuery, db: JobRepository) -> None:
    """Speichert Reject-Grund in SQLite + Auto-Location-Exclude nach 3x."""
    parts = callback.data.split(":")
    reason_type = parts[1]
    job_id = parts[2]

    reason_map = {
        "salary": "Gehalt zu niedrig",
        "location": "Zu weit weg",
        "role": "Falsche Rolle",
        "other": "Sonstiger Grund",
        "skip": "Kein Grund angegeben",
    }

    reason = reason_map.get(reason_type, "Unbekannt")

    # In DB speichern
    feedback = FeedbackEntry(
        job_id=job_id,
        action=ApplicationStatus.REJECTED,
        reason=reason,
        created_at=datetime.utcnow(),
    )
    await db.store_feedback(feedback)

    # Job-Status aktualisieren
    await db.update_job_status(job_id, ApplicationStatus.REJECTED)

    # Auto-exclude location nach 3x "Zu weit weg"
    if reason_type == "location":
        job = await db.get_job(job_id)
        if job and job.location:
            count = await db.count_location_rejections(job.location)
            if count >= 3:
                excluded = db.config.get("excluded_locations", []) if hasattr(db, "config") else []
                if job.location.lower() not in [l.lower() for l in excluded]:
                    excluded = list(excluded) + [job.location]
                    db.config["excluded_locations"] = excluded
                    await callback.message.answer(
                        f"⚠️ <b>Location automatisch ausgeschlossen:</b> {job.location}\n"
                        f"(3x 'Zu weit weg' gewählt)"
                    )

    # Nachricht aktualisieren
    await callback.message.edit_text(
        text=f"❌ <b>Abgelehnt</b>\nGrund: <i>{reason}</i>\n\n✅ Gespeichert für Learning Loop.",
        reply_markup=None,
    )
    await callback.answer("Gespeichert")

    logger.info(f"Job rejected: {job_id} – Reason: {reason}")
