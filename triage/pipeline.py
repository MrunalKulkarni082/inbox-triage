"""The orchestrator: runs every stage in order and records what happened.

    parse -> classify -> extract -> validate -> decide status -> draft -> store

One bad email never stops the run: it is caught, logged as a failure and
the rest of the inbox carries on.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import ai_classifier, classifier, drafter, extractor, llm_classifier, parser, validator
from .models import (Category, Classification, ProcessedEmail, RawEmail, RunReport, Severity, Status,
                     ValidationIssue)
from .storage import Store

log = logging.getLogger(__name__)


def decide_status(category: Category, issues, is_duplicate: bool) -> Status:
    """The routing rule, in one place, in priority order."""
    if is_duplicate:
        return Status.DUPLICATE
    if category == Category.SPAM:
        return Status.DISCARDED
    if validator.has_blocking_issue(issues):
        return Status.NEEDS_ATTENTION
    return Status.READY_FOR_REVIEW


class Timer:
    """Adds up the time spent in each stage across the whole run."""

    def __init__(self):
        self.totals: dict[str, float] = defaultdict(float)

    def __call__(self, stage: str):
        timer = self

        class _Ctx:
            def __enter__(self):
                self.t0 = time.perf_counter()

            def __exit__(self, *exc):
                timer.totals[stage] += (time.perf_counter() - self.t0) * 1000

        return _Ctx()


class RunState:
    """What the pipeline remembers while working through one run."""

    def __init__(self, store: Store, use_ai: bool, open_llm: str = "off"):
        self.known = store.known_fingerprints()     # processed in earlier runs
        self.seen_this_run: set[str] = set()        # processed earlier in this run
        self.senders_seen: dict[str, str] = {}      # sender -> first fingerprint
        self.order_ids_seen: dict[str, str] = {}    # order/ticket ID -> first file
        self.timer = Timer()
        self.ai_on = use_ai and ai_classifier.is_available()
        self.open_llm = open_llm  # "off", "uncertain" (only when rules are unsure) or "all"


OPEN_LLM_MODES = ("off", "uncertain", "all")


def combine(rules: Classification, ai: Classification | None) -> tuple[Classification, ValidationIssue | None]:
    """Decide between the rules and the AI's second opinion.

    - AI missing or unsure        -> keep the rules
    - both agree                  -> agreed category, higher confidence
    - rules unsure, AI confident  -> use the AI (this is where it helps most)
    - both confident but disagree -> keep the rules AND send to a person
    """
    if ai is None or ai.confidence < llm_classifier.MIN_CONFIDENCE:
        return rules, None
    if ai.category == rules.category:
        return Classification(
            category=ai.category, confidence=max(ai.confidence, rules.confidence),
            reasons=rules.reasons + [f"AI agrees ({ai.confidence:.0%}): " + "; ".join(ai.reasons)],
            method="rules+llm", scores=rules.scores,
        ), None
    if rules.category == Category.UNKNOWN:
        return Classification(
            category=ai.category, confidence=ai.confidence,
            reasons=ai.reasons + [f"rules were unsure ({rules.confidence:.0%}), so the AI answer is used"],
            method=ai.method, scores=rules.scores,
        ), None
    issue = ValidationIssue(
        field="category", severity=Severity.ERROR,
        message=(f"rules say '{rules.category.value}' ({rules.confidence:.0%}) but the AI says "
                 f"'{ai.category.value}' ({ai.confidence:.0%}) - a person should decide"),
    )
    return rules, issue


def process_email(raw: RawEmail, state: RunState) -> ProcessedEmail:
    """Stages 2-6 for one parsed email."""
    timer = state.timer
    with timer("2_classify"):
        cls = classifier.classify(raw)
        if state.ai_on:
            ai_cls = ai_classifier.classify_with_ai(raw)
            if ai_cls is not None:
                if ai_cls.category != cls.category:
                    ai_cls.reasons.append(f"rules said '{cls.category.value}' ({cls.confidence:.0%})")
                ai_cls.scores = cls.scores
                cls = ai_cls

        rules_cls, llm_cls, llm_note, disagreement = cls, None, None, None
        if state.open_llm == "all" or (state.open_llm == "uncertain" and cls.category == Category.UNKNOWN):
            llm_cls, llm_note = llm_classifier.classify_with_llm(raw)
            cls, disagreement = combine(cls, llm_cls)

    with timer("3_extract"):
        fields = extractor.extract(raw, cls.category)

    with timer("4_validate"):
        issues = validator.validate(
            raw, cls, fields,
            {"senders_seen": state.senders_seen, "order_ids_seen": state.order_ids_seen},
        )
        if disagreement:
            issues.append(disagreement)
        is_dup = raw.fingerprint in state.known or raw.fingerprint in state.seen_this_run
        status = decide_status(cls.category, issues, is_dup)

    with timer("6_draft"):
        reply = None
        if status in (Status.READY_FOR_REVIEW, Status.NEEDS_ATTENTION):
            reply = drafter.draft(raw, cls.category, fields, issues)

    state.seen_this_run.add(raw.fingerprint)
    state.senders_seen.setdefault(raw.sender_email, raw.fingerprint)
    if fields.order_id:
        state.order_ids_seen.setdefault(fields.order_id, raw.source_file)
    return ProcessedEmail(raw=raw, classification=cls, fields=fields,
                          issues=issues, status=status, draft_reply=reply,
                          rules_classification=rules_cls if llm_note else None,
                          ai_classification=llm_cls, ai_note=llm_note)


def run_single(raw: RawEmail, store: Store, use_ai: bool = False, open_llm: str = "off") -> RunReport:
    """Process one email (e.g. typed into the demo) and store it like any other."""
    return _run([raw], store, use_ai, open_llm)


def run(inbox_dir: Path, store: Store, use_ai: bool = False, open_llm: str = "off") -> RunReport:
    return _run(parser.load_inbox(inbox_dir), store, use_ai, open_llm)


def _run(items: list[Path] | list[RawEmail], store: Store, use_ai: bool, open_llm: str = "off") -> RunReport:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    run_id = started.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    assert open_llm in OPEN_LLM_MODES, open_llm
    state = RunState(store, use_ai, open_llm)
    timer, ai_on = state.timer, state.ai_on
    results: list[ProcessedEmail] = []
    failures: list[str] = []

    for item in items:
        name = item.name if isinstance(item, Path) else item.source_file
        try:
            if isinstance(item, Path):
                with timer("1_parse"):
                    raw = parser.parse_file(item)
            else:
                raw = item
            results.append(process_email(raw, state))
        except Exception as exc:  # one broken file must not stop the run
            log.exception("failed on %s", name)
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    finished = datetime.now(timezone.utc)
    report = RunReport(
        run_id=run_id,
        started_at=started,
        finished_at=finished,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        total=len(results),
        new_records=0,
        by_status=dict(Counter(r.status.value for r in results)),
        by_category=dict(Counter(r.classification.category.value for r in results)),
        issue_count=sum(len(r.issues) for r in results),
        ai_used=ai_on or any(r.ai_classification is not None for r in results),
        stage_timings_ms={k: round(v, 2) for k, v in sorted(timer.totals.items())},
        failures=failures,
        results=results,
    )

    with timer("5_store"):
        report.new_records = store.save_run(report, results)
    report.stage_timings_ms = {k: round(v, 2) for k, v in sorted(timer.totals.items())}
    return report
