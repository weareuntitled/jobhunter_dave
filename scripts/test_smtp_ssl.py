#!/usr/bin/env python3
"""scripts/test_smtp_ssl.py – Testet SMTP mit Port 465 (SSL) statt 587 (STARTTLS)."""

import asyncio
import os
import sys
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from aiosmtplib import send

async def test_smtp_ssl():
    print("📧 SMTP TEST (Port 465 SSL)")
    print("=" * 50)

    host = "mail.checkdomain.de"
    port = 465  # SSL Port
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM")
    recipient = sender

    if not password or password == "placeholder":
        print("❌ Passwort fehlt noch in .env!")
        return

    print(f"Server: {host}:{port}")
    print(f"Sender: {sender}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🧪 Job Hunter Agent – SMTP SSL Test"
    msg["From"] = sender
    msg["To"] = recipient

    text = """Hallo,

ich bin der lokale Automatisierungs-Agent von Daniel Peters.

Dies ist ein Test der SMTP-SSL-Verbindung (Port 465).
Wenn du diese E-Mail liest, funktioniert der Versand!

Mit freundlichen Gruessen,
Job Hunter Agent
"""

    msg.attach(MIMEText(text, "plain"))

    try:
        await send(
            msg,
            hostname=host,
            port=port,
            username=user,
            password=password,
            use_tls=True,  # SSL statt STARTTLS
        )
        print("✅ E-Mail erfolgreich versendet (SSL/465)!")
        print("   👉 Prüfe dein Postfach")

    except Exception as e:
        print(f"❌ SMTP-Fehler: {e}")
        print(f"   Typ: {type(e).__name__}")
        
        # Auch noch Port 25 probieren
        print("\n🔄 Versuche alternativ Port 25...")
        try:
            await send(
                msg,
                hostname=host,
                port=25,
                username=user,
                password=password,
                start_tls=True,
            )
            print("✅ E-Mail erfolgreich versendet (Port 25)!")
        except Exception as e2:
            print(f"❌ Auch Port 25 fehlgeschlagen: {e2}")
            print("\n📋 Checkdomain SMTP Einstellungen:")
            print("   Server: mail.checkdomain.de")
            print("   Ports: 587 (STARTTLS), 465 (SSL), 25")
            print("   SSL/TLS: JA")
            print("   Authentifizierung: JA (Normalpasswort)")
            print("\n💡 Tipp: Einloggen unter https://webmail.checkdomain.de")
            print("   und dort die korrekten Server-Einstellungen prüfen.")

    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_smtp_ssl())
