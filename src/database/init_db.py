"""src/database/init_db.py – SQLite Schema-Initialisierung und Verbindungs-Manager."""

from __future__ import annotations

import aiosqlite
from pathlib import Path

DB_PATH = Path("./db/job_hunter.db")


async def init_database() -> aiosqlite.Connection:
    """Erstellt alle Tabellen, wenn sie nicht existieren, und gibt die Connection zurück."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row  # Ermöglicht Column-Namen statt Indexes
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")

    # ── Jobs ────────────────────────────────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
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
        """
    )

    # ── Unique Hash für Deduplikation ───────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS job_hashes (
            hash TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
        """
    )

    # ── Feedback ────────────────────────────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
        """
    )

    # ── Agent State ─────────────────────────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            paused INTEGER DEFAULT 0,
            quiet_mode INTEGER DEFAULT 0,
            pause_until TIMESTAMP,
            last_hunt_at TIMESTAMP,
            total_api_calls_this_month INTEGER DEFAULT 0,
            api_budget_reached INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ── Audit Log ─────────────────────────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            job_id TEXT,
            details TEXT,
            level TEXT DEFAULT 'INFO'
        )
        """
    )

    # ── Error Log ──────────────────────────────────────────────────
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            component TEXT NOT NULL,
            error_type TEXT NOT NULL,
            message TEXT NOT NULL,
            job_id TEXT,
            retry_count INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0
        )
        """
    )

    # ── Indexe ──────────────────────────────────────────────────────
    await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_job ON feedback(job_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_log(job_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_error_job ON error_log(job_id)")

    # ── Default State ─────────────────────────────────────────────
    await db.execute(
        """
        INSERT OR IGNORE INTO agent_state (id, paused, quiet_mode)
        VALUES (1, 0, 0)
        """
    )

    await db.commit()
    return db
