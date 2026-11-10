import sys
from email.message import EmailMessage
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from triage.parser import parse_bytes  # noqa: E402

INBOX = ROOT / "data" / "sample_inbox"
LABELS = ROOT / "data" / "sample_labels.csv"


def make_email(body: str, subject: str = "Hello", sender: str = "Test Person <test@example.com>",
               attachments: tuple[str, ...] = (), html: bool = False,
               date: str = "Mon, 05 Oct 2026 10:00:00 +0530"):
    """Build a RawEmail in memory, so tests don't need files."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "inbox@example.com"
    msg["Subject"] = subject
    msg["Date"] = date
    msg.set_content(body, subtype="html" if html else "plain")
    for name in attachments:
        msg.add_attachment(b"x", maintype="application", subtype="pdf", filename=name)
    return parse_bytes(bytes(msg))


@pytest.fixture
def email_factory():
    return make_email
