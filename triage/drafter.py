"""Stage 6 - Draft a reply.

Fills a Jinja2 template for the email's category. Missing details become
visible placeholders like [confirm name] instead of being invented, and
warnings from validation turn into questions in the reply (for example,
asking for weekly hours when the candidate did not mention them).

Drafts are never sent. They wait for a person to approve, edit or reject.
"""

from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .models import Category, ExtractedFields, ProcessedEmail, RawEmail, Severity, ValidationIssue

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# Name used in reply sign-offs. Override with the TRIAGE_ORG_NAME env variable.
ORG_NAME = os.environ.get("TRIAGE_ORG_NAME", "Example Automation Co.")

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    undefined=StrictUndefined,  # a typo in a template fails loudly in tests
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)

TEMPLATES = {
    Category.INTERNSHIP: "internship.j2",
    Category.SALES_LEAD: "sales_lead.j2",
    Category.SUPPORT: "support.j2",
    Category.VENDOR: "vendor.j2",
    Category.UNKNOWN: "unknown.j2",
}


def first_name(full_name: str | None) -> str:
    if not full_name:
        return "[confirm name]"
    parts = full_name.replace(",", " ").split()
    if parts and parts[0].lower().rstrip(".") in {"dr", "prof"} and len(parts) > 1:
        return f"{parts[0].rstrip('.').title()}. {parts[-1].title()}"  # "Dr. Qureshi"
    parts = [p for p in parts if p.lower().rstrip(".") not in {"mr", "ms", "mrs"}]
    if not parts or "team" in full_name.lower():
        return "there" if parts else "[confirm name]"
    return parts[0].title()


def draft(email: RawEmail, category: Category, fields: ExtractedFields, issues: list[ValidationIssue]) -> str | None:
    template_name = TEMPLATES.get(category)
    if template_name is None:  # spam: no reply
        return None
    missing = {i.field for i in issues if i.severity in (Severity.WARNING, Severity.ERROR)}
    template = _env.get_template(template_name)
    return template.render(
        org_name=ORG_NAME,
        first_name=first_name(fields.name),
        f=fields,
        subject=email.subject,
        missing=missing,
    ).strip()


def redraft(record: ProcessedEmail) -> str | None:
    """Re-render a draft, e.g. after a reviewer corrects the category."""
    return draft(record.raw, record.classification.category, record.fields, record.issues)
