"""Stage 5 - Store.

Saves every processed email to SQLite. SQLite is a real SQL database stored
in a single file, so there is no server to install and the same queries
would work on PostgreSQL later.

Tables
  runs     one row per pipeline run (the audit log)
  emails   one row per unique email; `fingerprint` is UNIQUE, which is what
           stops re-runs creating duplicates
  issues   validation issues, many per email
  reviews  decisions a person made on a draft (approve / edit / reject)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import ProcessedEmail, RunReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL,
    total           INTEGER NOT NULL,
    new_records     INTEGER NOT NULL,
    issue_count     INTEGER NOT NULL,
    ai_used         INTEGER NOT NULL,
    by_status       TEXT NOT NULL,   -- JSON
    by_category     TEXT NOT NULL,   -- JSON
    stage_timings   TEXT NOT NULL,   -- JSON
    failures        TEXT NOT NULL    -- JSON
);

CREATE TABLE IF NOT EXISTS emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT NOT NULL UNIQUE,
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    source_file     TEXT NOT NULL,
    message_id      TEXT NOT NULL,
    received_at     TEXT,
    sender_name     TEXT,
    sender_email    TEXT,
    subject         TEXT,
    category        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    method          TEXT NOT NULL,
    reasons         TEXT NOT NULL,   -- JSON list
    status          TEXT NOT NULL,
    name            TEXT,
    organisation    TEXT,
    phone           TEXT,
    skills          TEXT,            -- JSON list
    graduation_year INTEGER,
    hours_per_week  INTEGER,
    order_id        TEXT,
    budget          TEXT,
    links           TEXT,            -- JSON list
    request_summary TEXT,
    draft_reply     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL REFERENCES emails(fingerprint),
    field       TEXT NOT NULL,
    severity    TEXT NOT NULL,
    message     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint  TEXT NOT NULL REFERENCES emails(fingerprint),
    decision     TEXT NOT NULL CHECK (decision IN ('approved', 'edited', 'rejected')),
    final_reply  TEXT,
    reviewed_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_emails_status   ON emails(status);
CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        """All-or-nothing writes: a crash mid-run leaves the DB unchanged."""
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---- reads -----------------------------------------------------------
    def known_fingerprints(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT fingerprint FROM emails")}

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Read-only query helper used by the UI's SQL tab."""
        if not sql.lstrip().lower().startswith(("select", "with")):
            raise ValueError("Only SELECT queries are allowed here.")
        return [dict(r) for r in self.conn.execute(sql, params)]

    # ---- writes ----------------------------------------------------------
    def save_run(self, report: RunReport, records: list[ProcessedEmail]) -> int:
        """Store the run and every new record. Returns how many were new."""
        new = 0
        with self.transaction() as c:
            c.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    report.run_id, report.started_at.isoformat(), report.finished_at.isoformat(),
                    report.duration_ms, report.total, report.new_records, report.issue_count,
                    int(report.ai_used), json.dumps(report.by_status), json.dumps(report.by_category),
                    json.dumps(report.stage_timings_ms), json.dumps(report.failures),
                ),
            )
            for rec in records:
                cur = c.execute(
                    """INSERT OR IGNORE INTO emails (
                        fingerprint, run_id, source_file, message_id, received_at, sender_name,
                        sender_email, subject, category, confidence, method, reasons, status,
                        name, organisation, phone, skills, graduation_year, hours_per_week,
                        order_id, budget, links, request_summary, draft_reply, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        rec.raw.fingerprint, report.run_id, rec.raw.source_file, rec.raw.message_id,
                        rec.raw.received_at.isoformat() if rec.raw.received_at else None,
                        rec.raw.sender_name, rec.raw.sender_email, rec.raw.subject,
                        rec.classification.category.value, rec.classification.confidence,
                        rec.classification.method, json.dumps(rec.classification.reasons),
                        rec.status.value, rec.fields.name, rec.fields.organisation, rec.fields.phone,
                        json.dumps(rec.fields.skills), rec.fields.graduation_year,
                        rec.fields.hours_per_week, rec.fields.order_id, rec.fields.budget,
                        json.dumps(rec.fields.links), rec.fields.request_summary,
                        rec.draft_reply, _now(),
                    ),
                )
                if cur.rowcount:  # 0 means the fingerprint already existed
                    new += 1
                    c.executemany(
                        "INSERT INTO issues (fingerprint, field, severity, message) VALUES (?,?,?,?)",
                        [(rec.raw.fingerprint, i.field, i.severity.value, i.message) for i in rec.issues],
                    )
            c.execute("UPDATE runs SET new_records = ? WHERE run_id = ?", (new, report.run_id))
        return new

    def record_review(self, fingerprint: str, decision: str, final_reply: str | None) -> None:
        with self.transaction() as c:
            c.execute(
                "INSERT INTO reviews (fingerprint, decision, final_reply, reviewed_at) VALUES (?,?,?,?)",
                (fingerprint, decision, final_reply, _now()),
            )

    def close(self) -> None:
        self.conn.close()
