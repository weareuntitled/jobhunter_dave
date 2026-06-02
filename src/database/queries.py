"""src/database/queries.py – Async CRUD-Operationen für SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from src.agent.schemas import (
    AgentState,
    ApplicationStatus,
    AuditLogEntry,
    ErrorLogEntry,
    FeedbackEntry,
    JobSource,
    RejectedJob,
    StoredJob,
    WeeklyKPI,
)

logger = logging.getLogger("job-hunter")


class JobRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def close(self) -> None:
        await self.db.close()

    # ── Jobs ────────────────────────────────────────────────────────

    async def store_job(
        self,
        job: StoredJob,
        job_hash: str | None = None,
    ) -> None:
        # Build column list and values dynamically
        columns = [
            "id", "title", "company", "url", "source", "description",
            "requirements", "location", "salary_range", "score", "status",
            "pdf_path", "cv_variant", "remote_type", "has_email_contact",
            "created_at", "updated_at"
        ]
        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(columns)

        values = [
            job.id,
            job.title,
            job.company,
            job.url,
            job.source.value,
            getattr(job, "description", None),
            json.dumps(getattr(job, "requirements", [])),
            getattr(job, "location", None),
            getattr(job, "salary_range", None),
            job.score,
            job.status.value,
            job.pdf_path,
            job.cv_variant,
            getattr(job, "remote_type", "hybrid"),
            1 if getattr(job, "has_email_contact", True) else 0,
            job.created_at.isoformat(),
            job.updated_at.isoformat(),
        ]

        await self.db.execute(
            f"INSERT OR REPLACE INTO jobs ({col_list}) VALUES ({placeholders})",
            values,
        )

        if job_hash:
            await self.db.execute(
                "INSERT OR IGNORE INTO job_hashes (hash, job_id) VALUES (?, ?)",
                (job_hash, job.id),
            )

        await self.db.commit()

    async def get_job(self, job_id: str) -> StoredJob | None:
        async with self.db.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_job(row)
            return None

    async def job_exists_by_hash(self, job_hash: str) -> bool:
        async with self.db.execute(
            "SELECT 1 FROM job_hashes WHERE hash = ?", (job_hash,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def get_jobs_by_status(
        self,
        status: ApplicationStatus,
        limit: int = 100,
    ) -> list[StoredJob]:
        async with self.db.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status.value, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    async def update_job_status(
        self,
        job_id: str,
        status: ApplicationStatus,
        pdf_path: str | None = None,
    ) -> None:
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = [status.value]

        if pdf_path:
            updates.append("pdf_path = ?")
            params.append(pdf_path)

        params.append(job_id)

        await self.db.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await self.db.commit()

    async def delete_old_unsent_jobs(self, retention_days: int = 7) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        await self.db.execute(
            """
            DELETE FROM jobs
            WHERE status = 'pending'
              AND created_at < ?
              AND pdf_path IS NOT NULL
            """,
            (cutoff,),
        )
        deleted = self.db.total_changes
        await self.db.commit()
        return deleted

    # ── Feedback ────────────────────────────────────────────────────

    async def store_feedback(self, feedback: FeedbackEntry) -> None:
        await self.db.execute(
            "INSERT INTO feedback (job_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
            (
                feedback.job_id,
                feedback.action.value,
                feedback.reason,
                feedback.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_recent_rejected(
        self,
        limit: int = 5,
    ) -> list[RejectedJob]:
        """Gibt die letzten abgelehnten Jobs zurück (für API-Kontext)."""
        async with self.db.execute(
            """
            SELECT j.id, j.title, j.company, j.score, f.reason, f.created_at
            FROM feedback f
            JOIN jobs j ON f.job_id = j.id
            WHERE f.action = 'rejected'
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                RejectedJob(
                    job_id=row[0],
                    job_title=row[1],
                    company=row[2],
                    score=row[3] or 0.0,
                    rejection_reason=row[4] or "Unbekannt",
                    rejected_at=datetime.fromisoformat(row[5]),
                )
                for row in rows
            ]

    async def count_location_rejections(self, location: str) -> int:
        """Zählt wie oft eine Location mit 'Zu weit weg' rejected wurde."""
        async with self.db.execute(
            """
            SELECT COUNT(*) FROM feedback f
            JOIN jobs j ON f.job_id = j.id
            WHERE f.action = 'rejected'
              AND f.reason = 'Zu weit weg'
              AND LOWER(j.location) = LOWER(?)
            """,
            (location,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def add_excluded_location(self, location: str) -> None:
        """Fügt eine Location zur Exclusion-Liste hinzu."""
        excluded = self.config.get("excluded_locations", []) if hasattr(self, "config") else []
        if not hasattr(self, "config"):
            self.config = {}
        excluded = list(excluded)
        if location.lower() not in [l.lower() for l in excluded]:
            excluded.append(location)
            self.config["excluded_locations"] = excluded
            logger.info(f"Location added to exclude list: {location}")

    # ── Agent State ───────────────────────────────────────────────

    async def get_agent_state(self) -> AgentState:
        async with self.db.execute(
            "SELECT * FROM agent_state WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return AgentState(
                    paused=bool(row[1]),
                    quiet_mode=bool(row[2]),
                    pause_until=datetime.fromisoformat(row[3]) if row[3] else None,
                    last_hunt_at=datetime.fromisoformat(row[4]) if row[4] else None,
                    total_api_calls_this_month=row[5] or 0,
                    api_budget_reached=bool(row[6]),
                    updated_at=datetime.fromisoformat(row[7]) if row[7] else datetime.utcnow(),
                )
            return AgentState()

    async def update_agent_state(self, state: AgentState) -> None:
        await self.db.execute(
            """
            UPDATE agent_state SET
                paused = ?,
                quiet_mode = ?,
                pause_until = ?,
                last_hunt_at = ?,
                total_api_calls_this_month = ?,
                api_budget_reached = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (
                int(state.paused),
                int(state.quiet_mode),
                state.pause_until.isoformat() if state.pause_until else None,
                state.last_hunt_at.isoformat() if state.last_hunt_at else None,
                state.total_api_calls_this_month,
                int(state.api_budget_reached),
            ),
        )
        await self.db.commit()

    # ── Audit Log ───────────────────────────────────────────────────

    async def log_event(self, entry: AuditLogEntry) -> None:
        await self.db.execute(
            """
            INSERT INTO audit_log (timestamp, event_type, job_id, details, level)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(),
                entry.event_type,
                entry.job_id,
                entry.details,
                entry.level,
            ),
        )
        await self.db.commit()

    # ── Error Log ──────────────────────────────────────────────────

    async def log_error(self, entry: ErrorLogEntry) -> None:
        await self.db.execute(
            """
            INSERT INTO error_log (timestamp, component, error_type, message, job_id, retry_count, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(),
                entry.component,
                entry.error_type,
                entry.message,
                entry.job_id,
                entry.retry_count,
                int(entry.resolved),
            ),
        )
        await self.db.commit()

    async def mark_error_resolved(self, error_id: int) -> None:
        await self.db.execute(
            "UPDATE error_log SET resolved = 1 WHERE id = ?",
            (error_id,),
        )
        await self.db.commit()

    # ── Weekly KPI ────────────────────────────────────────────────

    async def get_weekly_kpi(self) -> WeeklyKPI:
        now = datetime.utcnow()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59)

        async with self.db.execute(
            "SELECT COUNT(*) FROM jobs WHERE created_at >= ? AND created_at <= ?",
            (week_start.isoformat(), week_end.isoformat()),
        ) as cursor:
            jobs_scanned = (await cursor.fetchone())[0] or 0

        async with self.db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'sent' AND created_at >= ? AND created_at <= ?",
            (week_start.isoformat(), week_end.isoformat()),
        ) as cursor:
            proposals_sent = (await cursor.fetchone())[0] or 0

        async with self.db.execute(
            "SELECT COUNT(*) FROM feedback WHERE action = 'rejected' AND created_at >= ? AND created_at <= ?",
            (week_start.isoformat(), week_end.isoformat()),
        ) as cursor:
            rejects = (await cursor.fetchone())[0] or 0

        async with self.db.execute(
            "SELECT COUNT(*) FROM feedback WHERE action = 'accepted' AND created_at >= ? AND created_at <= ?",
            (week_start.isoformat(), week_end.isoformat()),
        ) as cursor:
            accepted = (await cursor.fetchone())[0] or 0

        async with self.db.execute(
            "SELECT AVG(score) FROM jobs WHERE created_at >= ? AND created_at <= ?",
            (week_start.isoformat(), week_end.isoformat()),
        ) as cursor:
            row = await cursor.fetchone()
            avg_score = round(row[0] or 0, 2)

        return WeeklyKPI(
            week_start=week_start,
            week_end=week_end,
            jobs_scanned=jobs_scanned,
            proposals_sent=proposals_sent,
            rejects=rejects,
            accepted=accepted,
            avg_score=avg_score,
            top_trends=[],  # Would require keyword analysis
            profile_tips_generated=0,  # Would require separate tracking
        )

    # ── Helpers ────────────────────────────────────────────────────

    def _row_to_job(self, row: aiosqlite.Row) -> StoredJob:
        """Konvertiert eine DB-Row in ein StoredJob-Objekt (mit Column-Namen)."""
        return StoredJob(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            url=row["url"],
            source=JobSource(row["source"]),
            description=row["description"],
            location=row["location"],
            salary_range=row["salary_range"],
            score=row["score"],
            status=ApplicationStatus(row["status"]),
            pdf_path=row["pdf_path"],
            cv_variant=row["cv_variant"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
        )
