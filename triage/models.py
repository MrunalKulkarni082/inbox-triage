"""Data models shared by every stage of the pipeline.

Each stage takes one of these objects in and hands a richer one out, so the
shape of the data at every step is explicit and validated by Pydantic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    INTERNSHIP = "internship"
    SALES_LEAD = "sales_lead"
    SUPPORT = "support"
    VENDOR = "vendor"
    SPAM = "spam"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    ERROR = "error"      # blocks the record: a person must look at it
    WARNING = "warning"  # record usable, but something looks off
    INFO = "info"        # worth knowing, no action needed


class Status(str, Enum):
    READY_FOR_REVIEW = "ready_for_review"  # draft ready, a person approves it
    NEEDS_ATTENTION = "needs_attention"    # low confidence or a blocking issue
    DUPLICATE = "duplicate"                # already processed earlier
    DISCARDED = "discarded"                # spam, no reply drafted


class RawEmail(BaseModel):
    """Stage 1 output: an email file turned into plain fields."""

    source_file: str
    message_id: str
    sender_name: str
    sender_email: str
    subject: str
    received_at: datetime | None
    body: str
    attachments: list[str] = Field(default_factory=list)
    fingerprint: str  # SHA-256 of normalised content, used for de-duplication


class Classification(BaseModel):
    """Stage 2 output: what kind of email this is, and why we think so."""

    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    method: str = "rules"  # "rules" or "ai"
    scores: dict[str, float] = Field(default_factory=dict)


class ExtractedFields(BaseModel):
    """Stage 3 output: structured details pulled out of the text."""

    name: str | None = None
    organisation: str | None = None
    email: str | None = None
    phone: str | None = None
    links: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    graduation_year: int | None = None
    hours_per_week: int | None = None
    order_id: str | None = None
    budget: str | None = None
    request_summary: str | None = None


class ValidationIssue(BaseModel):
    """Stage 4 output: one problem found in the extracted data."""

    field: str
    severity: Severity
    message: str


class ProcessedEmail(BaseModel):
    """Everything known about one email after the full pipeline."""

    raw: RawEmail
    classification: Classification
    fields: ExtractedFields
    issues: list[ValidationIssue] = Field(default_factory=list)
    status: Status
    draft_reply: str | None = None
    # Optional second opinion from an open-source LLM, kept for side-by-side display.
    rules_classification: Classification | None = None
    ai_classification: Classification | None = None
    ai_note: str | None = None


class RunReport(BaseModel):
    """Summary of one pipeline run, also written to the audit log."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    total: int
    new_records: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    issue_count: int
    ai_used: bool
    stage_timings_ms: dict[str, float]
    failures: list[str] = Field(default_factory=list)
    results: list[ProcessedEmail] = Field(default_factory=list)
