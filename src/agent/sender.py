"""src/agent/sender.py – Async SMTP E-Mail Sender mit Retry-Logik."""

from __future__ import annotations

import logging
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

logger = logging.getLogger("job-hunter")


class SMTPSender:
    def __init__(self, config: dict) -> None:
        self.host = os.environ.get(config["host_env"], "smtp.gmail.com")
        self.port = int(os.environ.get(config["port_env"], "587"))
        self.user = os.environ.get(config["user_env"], "")
        self.password = os.environ.get(config["password_env"], "")
        self.from_addr = os.environ.get(config["from_addr_env"], self.user)
        self.from_name = config.get("from_name", "Job Hunter Agent")

        retry_config = config.get("retry", {})
        self.max_attempts = retry_config.get("max_attempts", 3)
        self.backoff_seconds = retry_config.get("backoff", [300, 900, 2700])

    async def send(
        self,
        to_addr: str,
        subject: str,
        body: str,
        pdf_path: str | None = None,
        photo_path: str | None = None,
    ) -> bool:
        """Sendet eine E-Mail mit optionalem PDF- und Foto-Anhang.

        Returns True bei Erfolg, False nach allen Retry-Versuchen.
        """
        msg = self._build_message(
            to_addr=to_addr,
            subject=subject,
            body=body,
            pdf_path=pdf_path,
            photo_path=photo_path,
        )

        for attempt in range(self.max_attempts):
            try:
                await self._send_message(msg)
                logger.info(f"Email sent to {to_addr} (attempt {attempt + 1})")
                return True
            except Exception as e:
                wait = self.backoff_seconds[attempt] if attempt < len(self.backoff_seconds) else 300
                logger.warning(
                    f"SMTP send failed (attempt {attempt + 1}/{self.max_attempts}): {e}. "
                    f"Retrying in {wait}s..."
                )
                if attempt < self.max_attempts - 1:
                    import asyncio
                    await asyncio.sleep(wait)

        logger.error(f"Email to {to_addr} failed after {self.max_attempts} attempts")
        return False

    def _build_message(
        self,
        to_addr: str,
        subject: str,
        body: str,
        pdf_path: str | None = None,
        photo_path: str | None = None,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"{self.from_name} <{self.from_addr}>"
        msg["To"] = to_addr
        msg["Subject"] = subject

        # Text body
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # PDF attachment
        if pdf_path and Path(pdf_path).exists():
            pdf_data = Path(pdf_path).read_bytes()
            pdf_part = MIMEApplication(pdf_data, _subtype="pdf")
            pdf_part.add_header(
                "Content-Disposition",
                "attachment",
                filename=Path(pdf_path).name,
            )
            msg.attach(pdf_part)

        # Photo attachment
        if photo_path and Path(photo_path).exists():
            photo_data = Path(photo_path).read_bytes()
            photo_part = MIMEApplication(photo_data, _subtype="jpeg")
            photo_part.add_header(
                "Content-Disposition",
                "attachment",
                filename=Path(photo_path).name,
            )
            msg.attach(photo_part)

        return msg

    async def _send_message(self, msg: MIMEMultipart) -> None:
        """Sendet die Nachricht via SMTP."""
        async with aiosmtplib.SMTP(
            hostname=self.host,
            port=self.port,
            start_tls=True,
        ) as smtp:
            await smtp.login(self.user, self.password)
            await smtp.send_message(msg)
