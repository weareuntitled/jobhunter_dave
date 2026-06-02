"""src/telegram/routers/briefing.py – Sunday Briefing + Status Commands."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.database.queries import JobRepository
from src.telegram.formatters import format_briefing, format_status
from src.telegram.keyboards import control_keyboard

logger = logging.getLogger("job-hunter")
router = Router()


@router.message(Command("briefing"))
async def cmd_briefing(message: Message, db: JobRepository) -> None:
    """Manuelles Sunday Briefing."""
    kpi = await db.get_weekly_kpi()
    text = format_briefing(kpi)
    await message.answer(text)


@router.message(Command("status"))
async def cmd_status(message: Message, db: JobRepository) -> None:
    """Zeigt Agent-Status."""
    state = await db.get_agent_state()
    text = format_status(state.model_dump())
    await message.answer(text, reply_markup=control_keyboard())


@router.message(Command("pause"))
async def cmd_pause(message: Message, db: JobRepository) -> None:
    """Pausiert den Agenten."""
    from src.agent.schemas import AgentState

    state = await db.get_agent_state()
    state.paused = True
    await db.update_agent_state(state)
    await message.answer("⏸️ <b>Agent pausiert.</b> Keine neuen Hunt-Cycles.")


@router.message(Command("resume"))
async def cmd_resume(message: Message, db: JobRepository) -> None:
    """Setzt den Agenten fort."""
    from src.agent.schemas import AgentState

    state = await db.get_agent_state()
    state.paused = False
    state.pause_until = None
    await db.update_agent_state(state)
    await message.answer("▶️ <b>Agent aktiv.</b> Hunt-Cycles laufen wieder.")


@router.message(Command("quiet"))
async def cmd_quiet(message: Message, db: JobRepository) -> None:
    """Aktiviert Quiet-Mode."""
    from src.agent.schemas import AgentState

    state = await db.get_agent_state()
    state.quiet_mode = True
    await db.update_agent_state(state)
    await message.answer("🔕 <b>Quiet Mode aktiviert.</b> Vorschläge werden gesammelt.")


@router.message(Command("loud"))
async def cmd_loud(message: Message, db: JobRepository) -> None:
    """Deaktiviert Quiet-Mode."""
    from src.agent.schemas import AgentState

    state = await db.get_agent_state()
    state.quiet_mode = False
    await db.update_agent_state(state)
    await message.answer("🔔 <b>Loud Mode.</b> Vorschläge kommen sofort.")
