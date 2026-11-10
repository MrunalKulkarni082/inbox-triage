"""Stage 4 - Validate.

Checks the extracted record before anything is stored or drafted. The idea
is the same as cleaning a research dataset: never trust a field just because
a pattern produced it. Problems become *issues* with a severity, so they show
up in an exceptions report instead of silently ending up in the database.

Rules are plain functions in a list, so adding one is a few lines and each
rule can be tested on its own.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from .extractor import FREE_MAIL
from .models import Category, Classification, ExtractedFields, RawEmail, Severity, ValidationIssue

# Required fields per category. Missing ones become ERROR issues.
REQUIRED: dict[Category, list[str]] = {
    Category.INTERNSHIP: ["name", "email"],
    Category.SALES_LEAD: ["name", "email", "organisation"],
    Category.SUPPORT: ["email", "order_id"],
    Category.VENDOR: ["email"],
    Category.SPAM: [],
    Category.UNKNOWN: ["email"],
}

# Nice-to-have fields per category. Missing ones become WARNING issues.
RECOMMENDED: dict[Category, list[str]] = {
    Category.INTERNSHIP: ["skills", "graduation_year", "phone"],
    Category.SALES_LEAD: ["phone", "budget"],
    Category.SUPPORT: ["name"],
}

MIN_BODY_CHARS = 40

Context = dict  # shared state for rules, e.g. the reference date
Rule = Callable[[RawEmail, Classification, ExtractedFields, Context], list[ValidationIssue]]


def _issue(field: str, severity: Severity, message: str) -> ValidationIssue:
    return ValidationIssue(field=field, severity=severity, message=message)


def rule_required_fields(email, cls, f, ctx):
    out = []
    for name in REQUIRED.get(cls.category, []):
        if not getattr(f, name):
            out.append(_issue(name, Severity.ERROR, f"required field '{name}' is missing for a {cls.category.value} email"))
    for name in RECOMMENDED.get(cls.category, []):
        if not getattr(f, name):
            out.append(_issue(name, Severity.WARNING, f"'{name}' not found - reply may need to ask for it"))
    return out


def rule_body_length(email, cls, f, ctx):
    if len(email.body.strip()) == 0:
        return [_issue("body", Severity.ERROR, "email body is empty")]
    if len(email.body.strip()) < MIN_BODY_CHARS:
        return [_issue("body", Severity.WARNING, f"very short body ({len(email.body.strip())} characters)")]
    return []


def rule_email_format(email, cls, f, ctx):
    if f.email and not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", f.email):
        return [_issue("email", Severity.ERROR, f"sender address '{f.email}' is not a valid email")]
    return []


def rule_phone(email, cls, f, ctx):
    if not f.phone:
        return []
    digits = re.sub(r"\D", "", f.phone)
    if f.phone.startswith("+91") and len(digits) != 12:
        return [_issue("phone", Severity.WARNING, f"Indian number '{f.phone}' should have 10 digits after +91")]
    if not 10 <= len(digits) <= 13:
        return [_issue("phone", Severity.WARNING, f"phone '{f.phone}' has an unusual length ({len(digits)} digits)")]
    return []


def rule_graduation_year(email, cls, f, ctx):
    if f.graduation_year is None:
        return []
    ref_year = ctx["reference_date"].year
    if f.graduation_year < ref_year:
        return [_issue("graduation_year", Severity.WARNING,
                       f"graduation year {f.graduation_year} is in the past - check if they are a graduate, not a student")]
    if f.graduation_year > ref_year + 6:
        return [_issue("graduation_year", Severity.WARNING, f"graduation year {f.graduation_year} looks implausible")]
    return []


def rule_hours(email, cls, f, ctx):
    if f.hours_per_week is not None and not 1 <= f.hours_per_week <= 60:
        return [_issue("hours_per_week", Severity.WARNING, f"{f.hours_per_week} hours/week looks implausible")]
    return []


def rule_signature_mismatch(email, cls, f, ctx):
    """An address in the signature that differs from the sender is worth a note."""
    sig_emails = {e.lower() for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", email.body)}
    sig_emails.discard(email.sender_email)
    if sig_emails and cls.category != Category.SPAM:
        return [_issue("email", Severity.INFO, f"body also lists {', '.join(sorted(sig_emails))} - confirm the preferred reply address")]
    return []


def rule_free_mail_business(email, cls, f, ctx):
    domain = email.sender_email.split("@")[-1]
    if cls.category == Category.SALES_LEAD and domain in FREE_MAIL:
        return [_issue("email", Severity.INFO, "business enquiry sent from a personal mailbox - verify the company")]
    return []


def rule_low_confidence(email, cls, f, ctx):
    if cls.category == Category.UNKNOWN:
        return [_issue("category", Severity.ERROR, f"could not classify with enough confidence ({cls.confidence:.0%})")]
    return []


def rule_possible_repeat(email, cls, f, ctx):
    """Same sender, different content, in the same run: maybe a follow-up."""
    previous = ctx.get("senders_seen", {}).get(email.sender_email)
    if previous and previous != email.fingerprint:
        return [_issue("sender", Severity.INFO, "same sender appears more than once - may be a follow-up to an earlier email")]
    return []


def rule_linked_reference(email, cls, f, ctx):
    """Same order / ticket ID as an earlier email: link them, don't open a new case."""
    if f.order_id:
        earlier = ctx.get("order_ids_seen", {}).get(f.order_id)
        if earlier and earlier != email.source_file:
            return [_issue("order_id", Severity.INFO, f"{f.order_id} already raised in {earlier} - treat as the same case")]
    return []


RULES: list[Rule] = [
    rule_body_length,
    rule_required_fields,
    rule_email_format,
    rule_phone,
    rule_graduation_year,
    rule_hours,
    rule_signature_mismatch,
    rule_free_mail_business,
    rule_low_confidence,
    rule_possible_repeat,
    rule_linked_reference,
]


def validate(
    email: RawEmail,
    cls: Classification,
    fields: ExtractedFields,
    context: Context | None = None,
) -> list[ValidationIssue]:
    ctx = dict(context or {})
    ctx.setdefault("reference_date", email.received_at or datetime.now())
    issues: list[ValidationIssue] = []
    for rule in RULES:
        issues.extend(rule(email, cls, fields, ctx))
    return issues


def has_blocking_issue(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == Severity.ERROR for i in issues)
