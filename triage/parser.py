"""Stage 1 - Parse.

Turns a raw .eml file (the standard format every mail system can export) into
a RawEmail. Handles plain-text and HTML-only emails, attachments, odd
encodings, and missing headers without crashing.
"""

from __future__ import annotations

import hashlib
import html
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from .models import RawEmail

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(r"(?i)<\s*(br|/p|/div|/li|/tr|/h\d)\s*/?>")
_WS_RE = re.compile(r"[ \t]+")


def html_to_text(markup: str) -> str:
    """Very small HTML-to-text conversion: keep line breaks, drop tags."""
    text = _BLOCK_TAG_RE.sub("\n", markup)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _get_body(msg: EmailMessage) -> str:
    """Prefer the text/plain part; fall back to HTML converted to text."""
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        try:
            return plain.get_content().strip()
        except (LookupError, UnicodeDecodeError):
            payload = plain.get_payload(decode=True) or b""
            return payload.decode("utf-8", errors="replace").strip()
    rich = msg.get_body(preferencelist=("html",))
    if rich is not None:
        return html_to_text(rich.get_content())
    return ""


def fingerprint(sender_email: str, subject: str, body: str) -> str:
    """Stable ID for the *content* of an email.

    Whitespace and case are normalised so that the same email re-sent, or
    exported twice, gets the same fingerprint. This is what makes re-running
    the pipeline safe (idempotent).
    """
    normalised = "|".join(
        re.sub(r"\s+", " ", part).strip().lower()  # spaces, tabs AND line breaks
        for part in (sender_email, subject, body)
    )
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def parse_bytes(data: bytes, source_file: str = "<memory>") -> RawEmail:
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(data)  # type: ignore[assignment]

    sender_name, sender_email = parseaddr(str(msg.get("From", "")))
    subject = str(msg.get("Subject", "")).strip() or "(no subject)"
    body = _get_body(msg)

    received_at = None
    if msg.get("Date"):
        try:
            received_at = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            received_at = None

    attachments = [
        part.get_filename()
        for part in msg.iter_attachments()
        if part.get_filename()
    ]

    fp = fingerprint(sender_email, subject, body)
    message_id = str(msg.get("Message-ID", "")).strip() or f"<generated-{fp[:16]}>"

    return RawEmail(
        source_file=source_file,
        message_id=message_id,
        sender_name=sender_name.strip(),
        sender_email=sender_email.strip().lower(),
        subject=subject,
        received_at=received_at,
        body=body,
        attachments=attachments,
        fingerprint=fp,
    )


def from_text(sender_name: str, sender_email: str, subject: str, body: str,
              attachments: list[str] | None = None, label: str = "typed-in email") -> RawEmail:
    """Build a RawEmail from text typed into a form.

    It is turned into a real email message first and then parsed by the same
    code as .eml files, so typed-in emails go through exactly the same path.
    """
    from email.message import EmailMessage
    from email.utils import format_datetime
    from datetime import datetime

    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    msg["To"] = "inbox@example.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now().astimezone())
    msg.set_content(body or "")
    for name in attachments or []:
        msg.add_attachment(b"(placeholder)", maintype="application", subtype="octet-stream", filename=name)
    return parse_bytes(bytes(msg), source_file=label)


def parse_file(path: Path) -> RawEmail:
    return parse_bytes(path.read_bytes(), source_file=path.name)


def load_inbox(folder: Path) -> list[Path]:
    """All .eml files in a folder, in a stable (sorted) order."""
    return sorted(folder.glob("*.eml"))
