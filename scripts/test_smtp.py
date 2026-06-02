#!/usr/bin/env python3
"""scripts/test_smtp.py – Testet SMTP-Versand via Checkdomain."""

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

async def test_smtp():
    print("📧 SMTP TEST")
    print("=" * 50)

    host = os.environ.get("SMTP_HOST", "mail.checkdomain.de")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM")
    recipient = sender  # Test an dich selbst

    if not all([host, user, password, sender]):
        print("❌ SMTP-Credentials unvollständig!")
        return

    print(f"Server: {host}:{port}")
    print(f"Sender: {sender}")
    print(f"Recipient: {recipient}")

    # E-Mail bauen
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🧪 Job Hunter Agent – SMTP Test"
    msg["From"] = sender
    msg["To"] = recipient

    text_part = """Hallo,

ich bin der lokale Automatisierungs-Agent von Daniel Peters.

Dies ist ein Test der SMTP-Verbindung.
Wenn du diese E-Mail liest, funktioniert der Versand!

Mit freundlichen Gruessen,
Job Hunter Agent
"""

    html_part = """<html>
    <body style="font-family: Inter, Helvetica, Arial, sans-serif; color: #333;">
        <h2 style="color: #EC632B;">Job Hunter Agent – SMTP Test</h2>
        <p>Hallo,</p>
        <p>ich bin der <strong>lokale Automatisierungs-Agent</strong> von Daniel Peters.</p>
        <p>Dies ist ein Test der SMTP-Verbindung.<br>
        Wenn du diese E-Mail liest, funktioniert der Versand!</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 12px;">
            Versendet via aiosmtplib + Checkdomain<br>
            Portfolio: <a href="https://portfolio.untitled-ux.de">portfolio.untitled-ux.de</a>
        </p>
    </body>
</html>"""

    msg.attach(MIMEText(text_part, "plain"))
    msg.attach(MIMEText(html_part, "html"))

    try:
        await send(
            msg,
            hostname=host,
            port=port,
            username=user,
            password=password,
            start_tls=True,
        )
        print("✅ E-Mail erfolgreich versendet!")
        print(f"   An: {recipient}")
        print("   👉 Prüfe dein Postfach (auch Spam)")

    except Exception as e:
        print(f"❌ SMTP-Fehler: {e}")
        print(f"   Typ: {type(e).__name__}")
        if "authentication" in str(e).lower():
            print("   💡 Passwort prüfen – evtl. falsches Passwort oder App-Passwort nötig")
        elif "connection" in str(e).lower():
            print("   💡 Server/Port prüfen – evtl. SSL statt STARTTLS (Port 465)")

    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_smtp())
