"""src/telegram/bot.py – aiogram v3 Bot + Dispatcher Setup."""

from __future__ import annotations

import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault

logger = logging.getLogger("job-hunter")


async def set_bot_commands(bot: Bot) -> None:
    """Registriert die Bot-Kommandos für das Menü."""
    commands = [
        BotCommand(command="start", description="🤖 Willkommen & Übersicht"),
        BotCommand(command="hunt", description="🔍 Job-Suche starten"),
        BotCommand(command="jobs", description="📋 Gespeicherte Jobs"),
        BotCommand(command="stats", description="📊 Statistiken"),
        BotCommand(command="pause", description="⏸️ Agent pausieren"),
        BotCommand(command="resume", description="▶️ Agent fortsetzen"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info("📋 Bot commands registered")


def create_bot(config: dict) -> tuple[Bot, Dispatcher]:
    """Erstellt aiogram Bot und Dispatcher."""
    token = os.environ.get(config["bot_token_env"])
    if not token:
        raise ValueError(f"Telegram bot token not found in env var: {config['bot_token_env']}")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    logger.info("🤖 Telegram bot initialized")
    return bot, dp
