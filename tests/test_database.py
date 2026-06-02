"""tests/test_database.py – Tests für SQLite DB-Layer."""

import pytest
from datetime import datetime

from src.database.queries import JobRepository
from src.agent.schemas import (
    AgentState,
    ApplicationStatus,
    AuditLogEntry,
    ErrorLogEntry,
    FeedbackEntry,
    JobSource,
    StoredJob,
)


@pytest.fixture
async def db():
    """Erstellt eine frische In-Memory DB pro Test."""
    import aiosqlite
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row  # Ermöglicht Column-Namen statt Indexes

    # Create tables matching init_db.py schema
    await conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            description TEXT,
            requirements TEXT,
            location TEXT,
            salary_range TEXT,
            score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            pdf_path TEXT,
            cv_variant TEXT,
            remote_type TEXT DEFAULT 'hybrid',
            has_email_contact INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE job_hashes (hash TEXT PRIMARY KEY, job_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    """)
    await conn.execute("""
        CREATE TABLE feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE agent_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            paused INTEGER DEFAULT 0,
            quiet_mode INTEGER DEFAULT 0,
            pause_until TIMESTAMP,
            last_hunt_at TIMESTAMP,
            total_api_calls_this_month INTEGER DEFAULT 0,
            api_budget_reached INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            job_id TEXT,
            details TEXT,
            level TEXT DEFAULT 'INFO'
        )
    """)
    await conn.execute("""
        CREATE TABLE error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            component TEXT NOT NULL,
            error_type TEXT NOT NULL,
            message TEXT NOT NULL,
            job_id TEXT,
            retry_count INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0
        )
    """)
    await conn.execute("INSERT INTO agent_state (id, paused, quiet_mode) VALUES (1, 0, 0)")
    await conn.commit()

    repo = JobRepository(conn)
    yield repo
    await repo.close()


class TestJobRepository:
    @pytest.mark.asyncio
    async def test_store_and_retrieve_job(self, db):
        job = StoredJob(
            id="test123",
            title="UX Designer",
            company="TestCorp",
            url="https://example.com",
            source=JobSource.LINKEDIN,
            score=8.5,
            status=ApplicationStatus.PENDING,
        )
        await db.store_job(job, job_hash="hash123")

        retrieved = await db.get_job("test123")
        assert retrieved is not None
        assert retrieved.title == "UX Designer"
        assert retrieved.score == 8.5

    @pytest.mark.asyncio
    async def test_job_hash_deduplication(self, db):
        await db.store_job(StoredJob(
            id="job1", title="A", company="B", url="https://a.com",
            source=JobSource.INDEED, score=7.0, status=ApplicationStatus.PENDING,
        ), job_hash="dup_hash")

        exists = await db.job_exists_by_hash("dup_hash")
        assert exists is True

        exists2 = await db.job_exists_by_hash("new_hash")
        assert exists2 is False

    @pytest.mark.asyncio
    async def test_update_job_status(self, db):
        await db.store_job(StoredJob(
            id="job2", title="Test", company="Co", url="https://co.de",
            source=JobSource.STEPSTONE, score=6.0, status=ApplicationStatus.PENDING,
        ))

        await db.update_job_status("job2", ApplicationStatus.SENT, pdf_path="/tmp/test.pdf")

        updated = await db.get_job("job2")
        assert updated.status == ApplicationStatus.SENT

    @pytest.mark.asyncio
    async def test_feedback_and_retrieval(self, db):
        # Need to store job first since feedback uses job_id
        await db.store_job(StoredJob(
            id="job3", title="Test", company="Co", url="https://co.de",
            source=JobSource.LINKEDIN, score=7.0, status=ApplicationStatus.PENDING,
        ))

        await db.store_feedback(FeedbackEntry(
            job_id="job3",
            action=ApplicationStatus.REJECTED,
            reason="Salary too low",
            created_at=datetime.utcnow(),
        ))

        rejected = await db.get_recent_rejected(limit=5)
        assert len(rejected) == 1
        assert rejected[0].rejection_reason == "Salary too low"

    @pytest.mark.asyncio
    async def test_agent_state(self, db):
        state = await db.get_agent_state()
        assert state.paused is False
        assert state.total_api_calls_this_month == 0

        state.paused = True
        state.total_api_calls_this_month = 100
        await db.update_agent_state(state)

        updated = await db.get_agent_state()
        assert updated.paused is True
        assert updated.total_api_calls_this_month == 100

    @pytest.mark.asyncio
    async def test_audit_log(self, db):
        await db.log_event(AuditLogEntry(
            event_type="test_event",
            job_id="job4",
            details="Test details",
        ))
        # Audit log has no retrieval method yet, but insertion should not fail
        assert True

    @pytest.mark.asyncio
    async def test_error_log(self, db):
        await db.log_error(ErrorLogEntry(
            component="test",
            error_type="ValueError",
            message="Something went wrong",
            job_id="job5",
        ))
        # Error log has no retrieval method yet
        assert True
