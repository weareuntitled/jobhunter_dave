#!/usr/bin/env python3
"""scripts/test_smtp_quick.py – Schneller SMTP-Test mit kurzem Timeout."""

import asyncio
import os
import sys
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from aiosmtplib import SMTP

async def test_quick():
    print("📧 SMTP QUICK TEST")
    print("=" * 50)

    host = "mail.checkdomain.de"
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")

    if not password or password == "placeholder":
        print("❌ Passwort fehlt in .env!")
        return

    ports = [
        (587, "STARTTLS"),
        (465, "SSL/TLS"),
        (25, "STARTTLS"),
    ]

    for port, method in ports:
        print(f"\n🔄 Teste {host}:{port} ({method})...")
        try:
            client = SMTP(hostname=host, port=port, timeout=10)
            
            if port == 465:
                await client.connect(use_tls=True)
            else:
                await client.connect()
                if port == 587 or port == 25:
                    await client.starttls()
            
            await client.login(user, password)
            
            # Wenn wir hier sind, hat der Login funktioniert!
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "🧪 Job Hunter – SMTP Test"
            msg["From"] = user
            msg["To"] = user
            msg.attach(MIMEText("SMTP Test erfolgreich!", "plain"))
            
            await client.send_message(msg)
            await client.quit()
            
            print(f"✅ ERFOLGREICH! Port {port} ({method}) funktioniert!")
            print("   👉 Prüfe dein Postfach")
            return
            
        except Exception as e:
            print(f"   ❌ Fehlgeschlagen: {type(e).__name__}")
            print(f"      {str(e)[:100]}")
            continue

    print("\n" + "=" * 50)
    print("❌ Alle Ports fehlgeschlagen.")
    print("\n💡 Moegliche Ursachen:")
    print("   1. Falsches Passwort (im Webmail testen)")
    print("   2. SMTP-Zugriff bei Checkdomain deaktiviert")
    print("   3. 2FA aktiviert (dann App-Passwort noetig)")
    print("   4. Checkdomain erlaubt SMTP nur von bestimmten IPs")
    print("\n📋 Checkdomain Webmail: https://webmail.checkdomain.de")
    print("   Pruefe dort unter Einstellungen > SMTP/IMAP die Serverdaten")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_quick())
