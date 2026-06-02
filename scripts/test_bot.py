#!/usr/bin/env python3
"""scripts/test_bot.py – Prüft Telegram Bot Verbindung."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot

async def test_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "placeholder":
        print("❌ TELEGRAM_BOT_TOKEN nicht gesetzt!")
        return

    print(f"🔑 Token gefunden: {token[:20]}...")
    
    bot = Bot(token=token)
    
    try:
        me = await bot.get_me()
        print(f"✅ Bot verbunden!")
        print(f"   Name: {me.full_name}")
        print(f"   Username: @{me.username}")
        print(f"   ID: {me.id}")
        print(f"   Can join groups: {me.can_join_groups}")
        print(f"   Supports inline: {me.supports_inline_queries}")
        
        # Versuche Updates zu holen (zeigt letzte Interaktionen)
        updates = await bot.get_updates(limit=5)
        if updates:
            print(f"\n📨 Letzte {len(updates)} Updates:")
            for update in updates:
                if update.message:
                    chat_id = update.message.chat.id
                    user = update.message.from_user.username or update.message.from_user.full_name
                    text = update.message.text or "[no text]"
                    print(f"   Chat ID: {chat_id} | User: {user} | Text: {text[:50]}")
        else:
            print("\n📭 Keine Updates gefunden.")
            print("   👉 Schreibe @Jobhunter_daniel_bot eine Nachricht,")
            print("      dann kann ich deine Chat-ID auslesen.")
        
    except Exception as e:
        print(f"❌ Bot-Fehler: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_bot())
