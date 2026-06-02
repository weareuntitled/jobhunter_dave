"""src/agent/schemas.py – Pydantic v2 Modelle für den Go-API Datenaustausch."""

from __future__ import annotations

from datetime import datetime
try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ── Enums ─────────────────────────────────────────────────────────

class JobSource(StrEnum):
    LINKEDIN = "linkedin"
    STEPSTONE = "stepstone"
    INDEED = "indeed"


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    KEPT = "kept"
    SKIPPED = "skipped"


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


# ── Job-Modelle ───────────────────────────────────────────────────

class JobListing(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Eindeutige Job-ID (Hash aus URL + Titel)")
    title: str = Field(..., min_length=1, max_length=300)
    company: str = Field(..., min_length=1, max_length=200)
    location: str = Field(default="Remote")
    url: HttpUrl
    source: JobSource
    description: str = Field(..., min_length=10)
    requirements: list[str] = Field(default_factory=list)
    posted_date: datetime | None = None
    salary_range: str | None = None
    remote_type: WorkMode = WorkMode.HYBRID
    has_email_contact: bool = True
    contact_email: str | None = None


class JobSearchConfig(BaseModel):
    keywords: list[str] = Field(..., min_length=1)
    location: str = Field(default="Berlin, Germany")
    remote_only: bool = False
    results_per_site: int = Field(default=50, ge=1, le=200)
    sites: list[JobSource] = Field(default_factory=lambda: list(JobSource))
    exclude_portal_only: bool = True


# ── Profil-Modelle ────────────────────────────────────────────────

class ProfileSummary(BaseModel):
    name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    skills: list[str] = Field(..., min_length=1)
    experience_years: int = Field(..., ge=0)
    portfolio_url: str = Field(default="portfolio.untitled-ux.de")
    linkedin_url: str | None = None
    languages: list[str] = Field(default_factory=lambda: ["Deutsch", "Englisch"])
    raw_profile_md: str = Field(default="", description="Inhalt der master_profile.md")
    location: str = Field(default="Augsburg, Germany")
    work_mode: WorkMode = WorkMode.REMOTE
    salary_min: int = Field(default=56000, ge=0)
    salary_max: int = Field(default=70000, ge=0)
    photo_included: bool = True


# ── Evaluate Request ──────────────────────────────────────────────

class RejectedJob(BaseModel):
    job_title: str
    company: str
    rejection_reason: str = Field(..., min_length=5)
    score: float = Field(..., ge=0, le=10)
    rejected_at: datetime


class EvaluateRequest(BaseModel):
    job: JobListing
    profile: ProfileSummary
    rejected_context: list[RejectedJob] = Field(
        default_factory=list,
        max_length=5,
        description="Die letzten 5 abgelehnten Jobs für Auto-Alignment",
    )
    instruction: str = Field(
        default="Verfasse das Anschreiben aus der Perspektive des "
                "Automatisierungs-Agenten. Adaptive Mirroring aktivieren.",
    )
    cv_variants: list[str] = Field(
        default_factory=list,
        description="Verfügbare CV-Varianten in /data/cv/",
    )
    voice_samples: list[str] = Field(
        default_factory=list,
        description="Text-Samples der Stimme für Stil-Referenz",
    )
    application_language: str = Field(
        default="de",
        description="Sprache der Bewerbung: de oder en",
    )


# ── Evaluate Response ─────────────────────────────────────────────

class EvaluateResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    score: float = Field(..., ge=0, le=10)
    reasoning: str = Field(..., min_length=10)
    adapted_cover_letter: str = Field(..., min_length=50)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    profile_tip: str | None = Field(
        default=None,
        description="Vorschlag für Profil-Erweiterung bei Top-Jobs (Score > 8)",
    )
    agent_voice_confidence: float = Field(
        default=0.0, ge=0, le=1,
        description="Wie gut die Agenten-Stimme getroffen wurde",
    )
    selected_cv_variant: str | None = Field(
        default=None,
        description="Empfohlene CV-Variante aus /data/cv/",
    )
    is_duplicate_of: str | None = Field(
        default=None,
        description="Job-ID des Duplikats, falls vorhanden",
    )


# ── CV Variant Models ─────────────────────────────────────────────

class CVVariant(BaseModel):
    name: str
    file_path: str
    description: str
    suitable_for: list[str] = Field(default_factory=list)


class CVSelectionRequest(BaseModel):
    job: JobListing
    available_variants: list[CVVariant]


class CVSelectionResponse(BaseModel):
    selected_variant: CVVariant
    adaptation_notes: str | None = None


# ── Telegram Dispatch ──────────────────────────────────────────────

class DispatchPayload(BaseModel):
    job: JobListing
    evaluation: EvaluateResponse
    pdf_path: str
    action: Literal["send_smtp", "open_portal", "reject"] | None = None


# ── Sunday Briefing ───────────────────────────────────────────────

class WeeklyKPI(BaseModel):
    week_start: datetime
    week_end: datetime
    jobs_scanned: int = Field(..., ge=0)
    proposals_sent: int = Field(..., ge=0)
    rejects: int = Field(..., ge=0)
    accepted: int = Field(..., ge=0)
    avg_score: float = Field(..., ge=0, le=10)
    top_trends: list[str] = Field(default_factory=list)
    profile_tips_generated: int = Field(default=0, ge=0)
    applications_sent: int = Field(default=0, ge=0)
    top_jobs: list[dict] = Field(default_factory=list)


# ── Database Row Models ───────────────────────────────────────────

class StoredJob(BaseModel):
    id: str
    title: str
    company: str
    url: str
    source: JobSource
    score: float
    location: str | None = None
    description: str | None = None
    salary_range: str | None = None
    status: ApplicationStatus = ApplicationStatus.PENDING
    pdf_path: str | None = None
    cv_variant: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackEntry(BaseModel):
    id: int | None = None
    job_id: str
    action: ApplicationStatus
    reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Agent State ──────────────────────────────────────────────────

class AgentState(BaseModel):
    paused: bool = False
    quiet_mode: bool = False
    pause_until: datetime | None = None
    last_hunt_at: datetime | None = None
    total_api_calls_this_month: int = 0
    api_budget_reached: bool = False
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Audit Log ────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., min_length=1)
    job_id: str | None = None
    details: str | None = None
    level: str = Field(default="INFO")


# ── Error Log ─────────────────────────────────────────────────────

class ErrorLogEntry(BaseModel):
    id: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    component: str = Field(..., min_length=1)
    error_type: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    job_id: str | None = None
    retry_count: int = 0
    resolved: bool = False
