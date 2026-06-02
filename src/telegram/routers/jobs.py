"""src/telegram/routers/jobs.py – Job-Vorschläge + Inline-Buttons Handler."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from src.agent.schemas import ApplicationStatus, StoredJob
from src.agent.sender import SMTPSender
from src.database.queries import JobRepository
from src.telegram.keyboards import (
    confirm_send_keyboard,
    job_proposal_keyboard,
)

logger = logging.getLogger("job-hunter")
router = Router()


async def send_job_proposal(
    bot,
    chat_id: int,
    job: StoredJob,
    evaluation: dict,
    pdf_path: str,
) -> Message:
    """Sendet einen Job-Vorschlag an den User."""
    msg = (
        f"🎯 <b>{job.title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 {job.company}\n"
        f"⭐ Score: <b>{job.score:.1f}/10</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    pdf_file = FSInputFile(pdf_path)
    await bot.send_document(
        chat_id=chat_id,
        document=pdf_file,
        caption=msg,
        reply_markup=job_proposal_keyboard(job.id),
    )

    logger.info(f"Job proposal sent: {job.title} @ {job.company}")


@router.callback_query(F.data.startswith("send:"))
async def handle_send(callback: CallbackQuery, db: JobRepository) -> None:
    """Handler für [🚀 Senden] Button."""
    job_id = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=confirm_send_keyboard(job_id))
    await callback.answer("Bitte bestätigen")


@router.callback_query(F.data.startswith("confirm_send:"))
async def handle_confirm_send(
    callback: CallbackQuery,
    db: JobRepository,
    smtp: SMTPSender,
) -> None:
    """Bestätigtes Senden via SMTP."""
    job_id = callback.data.split(":")[1]
    job = await db.get_job(job_id)

    if not job:
        await callback.answer("Job nicht gefunden")
        return

    # SMTP-Versand
    subject = f"Bewerbung als {job.title} – Daniel Peters"
    body = "Hallo,\n\nanbei meine Bewerbungsunterlagen.\n\nMit freundlichen Grüßen\nDaniel Peters"

    photo_path = "./data/photo.jpg"
    # Extract email from job description or use fallback
    to_addr = job.contact_email or "bewerbung@company.de"
    success = await smtp.send(
        to_addr=to_addr,
        subject=subject,
        body=body,
        pdf_path=job.pdf_path,
        photo_path=photo_path,
    )

    if success:
        await db.update_job_status(job_id, ApplicationStatus.SENT)
        await callback.message.edit_text(
            text=callback.message.text + "\n\n✅ <b>Bewerbung gesendet!</b>",
            reply_markup=None,
        )
        await callback.answer("Bewerbung gesendet")
        logger.info(f"Application sent via SMTP: {job_id}")
    else:
        await db.update_job_status(job_id, ApplicationStatus.REJECTED)
        await callback.message.edit_text(
            text=callback.message.text + "\n\n⚠️ <b>Versand fehlgeschlagen.</b> Bitte später erneut versuchen.",
            reply_markup=None,
        )
        await callback.answer("SMTP-Fehler")
        logger.error(f"SMTP send failed: {job_id}")


@router.callback_query(F.data.startswith("portal:"))
async def handle_portal(callback: CallbackQuery, db: JobRepository) -> None:
    """Handler für [🔗 Portal Link] Button."""
    job_id = callback.data.split(":")[1]
    job = await db.get_job(job_id)

    if job:
        # TODO: Google-Suche Fallback falls keine direkte URL
        await callback.answer(f"Öffne: {job.url}")
    else:
        await callback.answer("Job nicht gefunden")


@router.callback_query(F.data.startswith("edit:"))
async def handle_edit(callback: CallbackQuery, db: JobRepository) -> None:
    """Handler für [✏️ Bearbeiten] Button."""
    job_id = callback.data.split(":")[1]
    await callback.message.edit_text(
        text=f"✏️ <b>Bearbeitung gewünscht</b>\n\nBitte sende deine Änderungen als Antwort. Der Agent generiert ein neues PDF.",
        reply_markup=None,
    )
    await callback.answer("Bearbeitungsmodus aktiv")


@router.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery, db: JobRepository) -> None:
    """Zurück zur Übersicht."""
    job_id = callback.data.split(":")[1]
    job = await db.get_job(job_id)

    if job:
        await callback.message.edit_reply_markup(
            reply_markup=job_proposal_keyboard(job_id),
        )
    await callback.answer("Zurück")
