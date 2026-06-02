"""tests/test_telegram.py – Tests für Telegram Formatters & Keyboards."""

import pytest
from datetime import datetime
from src.agent.schemas import WeeklyKPI
from src.telegram.formatters import format_briefing, format_job_proposal, format_status
from src.telegram.keyboards import job_proposal_keyboard, reject_reason_keyboard, control_keyboard


class TestFormatters:
    def test_format_job_proposal(self):
        from src.agent.schemas import JobListing, JobSource
        job = JobListing(
            id="test",
            title="Senior UX Designer",
            company="TechCorp",
            location="Berlin",
            url="https://example.com",
            source=JobSource.LINKEDIN,
            description="Test description",
        )
        text = format_job_proposal(
            job=job,
            score=8.5,
            bullets=["Figma", "UX", "Agile"],
        )
        assert "Senior UX Designer" in text
        assert "TechCorp" in text
        assert "8.5/10" in text
        assert "Figma" in text

    def test_format_briefing(self):
        kpi = WeeklyKPI(
            week_start=datetime(2024, 1, 1),
            week_end=datetime(2024, 1, 7),
            jobs_scanned=50,
            proposals_sent=10,
            rejects=3,
            accepted=1,
            avg_score=7.5,
            top_trends=["Figma", "Remote"],
            profile_tips_generated=2,
        )
        text = format_briefing(kpi)
        assert "Sunday Briefing" in text
        assert "50" in text
        assert "Figma" in text
        assert "7.5" in text

    def test_format_status(self):
        state = {
            "paused": False,
            "quiet_mode": True,
            "total_api_calls_this_month": 150,
            "api_budget_reached": False,
        }
        text = format_status(state)
        assert "Aktiv" in text
        assert "Quiet" in text
        assert "150" in text


class TestKeyboards:
    def test_job_proposal_keyboard(self):
        kb = job_proposal_keyboard("job123")
        assert len(kb.inline_keyboard) == 2  # 2 rows
        assert kb.inline_keyboard[0][0].text == "🚀 Senden (SMTP)"
        assert kb.inline_keyboard[0][0].callback_data == "send:job123"

    def test_reject_reason_keyboard(self):
        kb = reject_reason_keyboard("job456")
        assert len(kb.inline_keyboard) == 3  # 3 rows
        assert kb.inline_keyboard[2][0].text == "⏭️ Skip Grund"

    def test_control_keyboard(self):
        kb = control_keyboard()
        assert len(kb.inline_keyboard) == 3  # 3 rows
        assert kb.inline_keyboard[0][0].text == "⏸️ /pause"
