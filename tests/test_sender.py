"""tests/test_sender.py – Tests für SMTP Sender mit Retry-Logik."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from email.mime.application import MIMEApplication

from src.agent.sender import SMTPSender


@pytest.fixture
def smtp_config():
    return {
        "host_env": "SMTP_HOST",
        "port_env": "SMTP_PORT",
        "user_env": "SMTP_USER",
        "password_env": "SMTP_PASSWORD",
        "from_addr_env": "SMTP_FROM",
        "from_name": "Test Sender",
        "retry": {
            "max_attempts": 3,
            "backoff": [0.01, 0.01, 0.01],  # Schnell für Tests
        },
    }


@pytest.fixture
def tmp_pdf(tmp_path: Path) -> str:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake pdf content")
    return str(pdf)


@pytest.fixture
def tmp_photo(tmp_path: Path) -> str:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0 fake jpeg content")
    return str(photo)


class TestSMTPSenderInit:
    def test_reads_env_vars(self, smtp_config, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "user@test.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        monkeypatch.setenv("SMTP_FROM", "from@test.com")

        sender = SMTPSender(smtp_config)
        assert sender.host == "smtp.test.com"
        assert sender.port == 465
        assert sender.user == "user@test.com"
        assert sender.password == "secret"
        assert sender.from_addr == "from@test.com"

    def test_defaults_when_env_missing(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)
        assert sender.host == "smtp.gmail.com"
        assert sender.port == 587


class TestBuildMessage:
    def test_message_with_all_attachments(self, smtp_config, tmp_pdf, tmp_photo, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)
        msg = sender._build_message(
            to_addr="recipient@test.com",
            subject="Bewerbung als UX Designer – Daniel",
            body="Hallo,\n\nanbei meine Bewerbungsunterlagen.\n\nMit freundlichen Grüßen\nDaniel Peters",
            pdf_path=tmp_pdf,
            photo_path=tmp_photo,
        )

        assert msg["To"] == "recipient@test.com"
        assert "Bewerbung als UX Designer" in msg["Subject"]
        assert len(msg.get_payload()) == 3  # body + pdf + photo

    def test_message_without_attachments(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)
        msg = sender._build_message(
            to_addr="recipient@test.com",
            subject="Test Subject",
            body="Plain text body",
        )

        assert len(msg.get_payload()) == 1  # body only

    def test_message_ignores_nonexistent_pdf(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)
        msg = sender._build_message(
            to_addr="recipient@test.com",
            subject="Test",
            body="Body",
            pdf_path="/nonexistent/path/file.pdf",
        )

        assert len(msg.get_payload()) == 1  # body only, no pdf


class TestSend:
    @pytest.mark.asyncio
    async def test_successful_send(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)

        mock_smtp_instance = AsyncMock()
        mock_smtp_class = MagicMock()
        mock_smtp_class.return_value.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
        mock_smtp_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.agent.sender.aiosmtplib.SMTP", mock_smtp_class):
            result = await sender.send(
                to_addr="recipient@test.com",
                subject="Test Subject",
                body="Test Body",
            )

            assert result is True
            mock_smtp_instance.login.assert_called_once()
            mock_smtp_instance.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)

        send_attempts = 0

        async def failing_then_success(*args, **kwargs):
            nonlocal send_attempts
            send_attempts += 1
            if send_attempts < 2:
                raise ConnectionError("Temporary network issue")

        mock_smtp_instance = AsyncMock()
        mock_smtp_instance.send_message = failing_then_success

        mock_smtp_class = MagicMock()
        mock_smtp_class.return_value.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
        mock_smtp_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.agent.sender.aiosmtplib.SMTP", mock_smtp_class):
            result = await sender.send(
                to_addr="recipient@test.com",
                subject="Test",
                body="Body",
            )

            assert result is True
            assert send_attempts == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, smtp_config, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)

        mock_smtp_instance = AsyncMock()
        mock_smtp_instance.login.side_effect = ConnectionError("Permanent failure")

        mock_smtp_class = MagicMock()
        mock_smtp_class.return_value.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
        mock_smtp_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.agent.sender.aiosmtplib.SMTP", mock_smtp_class):
            result = await sender.send(
                to_addr="recipient@test.com",
                subject="Test",
                body="Body",
            )

            assert result is False
            assert mock_smtp_instance.login.call_count == 3  # All 3 attempts

    @pytest.mark.asyncio
    async def test_send_with_pdf_attachment(self, smtp_config, tmp_pdf, monkeypatch):
        for var in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
            monkeypatch.delenv(var, raising=False)

        sender = SMTPSender(smtp_config)

        mock_smtp_instance = AsyncMock()
        mock_smtp_class = MagicMock()
        mock_smtp_class.return_value.__aenter__ = AsyncMock(return_value=mock_smtp_instance)
        mock_smtp_class.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("src.agent.sender.aiosmtplib.SMTP", mock_smtp_class):
            await sender.send(
                to_addr="recipient@test.com",
                subject="Bewerbung",
                body="Body",
                pdf_path=tmp_pdf,
            )

            send_call = mock_smtp_instance.send_message.call_args
            msg = send_call[0][0]
            attachments = [p for p in msg.get_payload() if isinstance(p, MIMEApplication)]
            assert len(attachments) == 1
            assert "test.pdf" in str(attachments[0].get_filename())
