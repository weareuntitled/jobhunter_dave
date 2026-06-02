"""src/telegram/keyboards.py – InlineKeyboard Markup-Builder."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.agent.schemas import ApplicationStatus


def job_proposal_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Inline-Buttons für einen Job-Vorschlag."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Senden (SMTP)",
                    callback_data=f"send:{job_id}",
                ),
                InlineKeyboardButton(
                    text="🔗 Portal Link",
                    callback_data=f"portal:{job_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Bearbeiten",
                    callback_data=f"edit:{job_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"reject:{job_id}",
                ),
            ],
        ]
    )


def reject_reason_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Buttons für Reject-Grund (optional)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Gehalt zu niedrig",
                    callback_data=f"reject_reason:salary:{job_id}",
                ),
                InlineKeyboardButton(
                    text="📍 Zu weit weg",
                    callback_data=f"reject_reason:location:{job_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👤 Falsche Rolle",
                    callback_data=f"reject_reason:role:{job_id}",
                ),
                InlineKeyboardButton(
                    text="📝 Sonstiges",
                    callback_data=f"reject_reason:other:{job_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏭️ Skip Grund",
                    callback_data=f"reject_reason:skip:{job_id}",
                ),
            ],
        ]
    )


def confirm_send_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Bestätigungs-Buttons vor dem Senden."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ja, senden",
                    callback_data=f"confirm_send:{job_id}",
                ),
                InlineKeyboardButton(
                    text="⬅️ Zurück",
                    callback_data=f"back:{job_id}",
                ),
            ],
        ]
    )


def edit_done_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Buttons nach dem Bearbeiten."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Senden",
                    callback_data=f"send:{job_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"reject:{job_id}",
                ),
            ],
        ]
    )


def control_keyboard() -> InlineKeyboardMarkup:
    """Steuerungs-Buttons im Chat."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏸️ /pause",
                    callback_data="cmd:pause",
                ),
                InlineKeyboardButton(
                    text="▶️ /resume",
                    callback_data="cmd:resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔕 /quiet",
                    callback_data="cmd:quiet",
                ),
                InlineKeyboardButton(
                    text="🔔 /loud",
                    callback_data="cmd:loud",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 /status",
                    callback_data="cmd:status",
                ),
                InlineKeyboardButton(
                    text="📈 /stats",
                    callback_data="cmd:stats",
                ),
            ],
        ]
    )
