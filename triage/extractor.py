"""Stage 3 - Extract.

Pulls structured fields out of free text using patterns. Every field is
optional: if something is not in the email we leave it empty rather than
guess. Deciding whether an empty field is a *problem* is the validator's job,
not the extractor's - keeping the two apart makes each easy to test.
"""

from __future__ import annotations

import re

from .models import Category, ExtractedFields, RawEmail

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Indian and international phone numbers, with spaces/dashes allowed.
PHONE_RE = re.compile(r"(?<![\w])(\+?\d[\d\s\-()]{8,16}\d)(?![\w])")
URL_RE = re.compile(r"https?://[^\s<>\"')]+")
GRAD_YEAR_RE = re.compile(
    r"(?:graduat\w*|class of|batch of|passing out|complete my degree)\D{0,25}(20\d\d)",
    re.IGNORECASE,
)
HOURS_RE = re.compile(r"(\d{1,2})\s*(?:-|to)?\s*(?:\d{1,2})?\s*(?:hours|hrs)\s*(?:a|per|/)\s*week", re.IGNORECASE)
ORDER_RE = re.compile(r"\b((?:ORD|INV|TKT)[- #]?\d{3,}|#\d{4,})\b", re.IGNORECASE)
BUDGET_RE = re.compile(
    r"(₹\s?[\d,.]+\s?(?:lakh|lakhs|cr|crore|k)?|\$\s?[\d,.]+\s?k?|\b[\d.]+\s?(?:lakh|lakhs)\b|"
    r"(?:INR|USD|Rs\.?)\s?[\d,.]+\s?(?:lakh|k)?)",
    re.IGNORECASE,
)
SIGNOFF_RE = re.compile(
    r"^(?:best regards|kind regards|regards|warm regards|thanks(?: and regards)?|thank you|sincerely|cheers|best),?\s*$",
    re.IGNORECASE,
)

# Skills vocabulary: canonical name -> pattern. Matching against a fixed list
# keeps the output clean ("Power BI", never "powerbi" and "PowerBI").
SKILLS: dict[str, str] = {
    "Python": r"\bpython\b",
    "SQL": r"\bsql\b",
    "R": r"(?<![\w-])R(?![\w-])(?=[,/ ]|$)",
    "Excel": r"\bexcel\b",
    "Power BI": r"\bpower\s?bi\b",
    "Tableau": r"\btableau\b",
    "Stata": r"\bstata\b",
    "JavaScript": r"\bjavascript\b|\bjs\b",
    "React": r"\breact\b",
    "Java": r"\bjava\b(?!script)",
    "Machine Learning": r"\bmachine learning\b|\bml\b",
    "n8n": r"\bn8n\b",
    "Zapier": r"\bzapier\b",
    "Make.com": r"\bmake\.com\b",
    "APIs": r"\bapis?\b|\brest\b",
    "Pandas": r"\bpandas\b",
    "Docker": r"\bdocker\b",
    "Figma": r"\bfigma\b",
}

FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me", "icloud.com", "rediffmail.com"}

# Known domains -> organisation names. In a real deployment this would be a
# lookup table maintained by the team (or a CRM).
# (The sample data uses fictional organisations.)
KNOWN_DOMAINS = {
    "greenfield.ac.in": "Greenfield Institute of Technology",
    "lakeview.edu": "Lakeview University",
    "nsis.ac.in": "National School of Inference Sciences",
    "sunrise-clinic.in": "Sunrise Family Clinic",
}


def _signature_block(body: str) -> list[str]:
    """Lines after the last sign-off ("Best regards," etc.)."""
    lines = [l.strip() for l in body.splitlines()]
    for i in range(len(lines) - 1, -1, -1):
        if SIGNOFF_RE.match(lines[i]):
            return [l for l in lines[i + 1 :] if l][:8]
    return []


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+91" + digits  # assume India for bare 10-digit numbers
    return digits or None


def _organisation(email: RawEmail, signature: list[str]) -> str | None:
    domain = email.sender_email.split("@")[-1]
    if domain in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[domain]
    # "Operations Lead, Urban Threads" -> "Urban Threads"
    for line in signature[1:]:
        m = re.match(r"^[\w ]*\b(lead|manager|director|head|founder|ceo|cto|coordinator|owner|partner)\b[\w ]*,\s*(.+)$", line, re.I)
        if m:
            return m.group(2).strip()
    # Signature lines that look like an organisation.
    for line in signature[1:]:
        if re.search(r"\b(pvt|ltd|llp|inc|university|institute|college|clinic|technologies|solutions|labs|foods|logistics|traders|hospital)\b", line, re.I):
            return line.split("|")[0].split(",")[-1].strip() if "," in line else line.split("|")[0].strip()
    if domain and domain not in FREE_MAIL:
        root = domain.split(".")[0]
        return root.replace("-", " ").title()
    return None


ASK_RE = re.compile(
    r"\b(we want|we would like|i would like|could you|can you|can we|please|looking for|interested in|need|stopped|not working|failing|error)\b",
    re.IGNORECASE,
)


def _summary(email: RawEmail) -> str:
    """One-line summary: the first sentence that actually asks for something.

    Falls back to the first sentence. Greetings and sign-offs are skipped.
    """
    body = email.body.split("---------- Forwarded message")[0]
    text = re.sub(r"\s+", " ", body).strip()
    text = re.sub(r"^(dear|hi|hello|hey|namaste)\b[^,.!]*[,.!]\s*", "", text, flags=re.I)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s", text) if len(s.strip()) > 3]
    if not sentences:
        return ""
    for s in sentences:
        if ASK_RE.search(s) and not SIGNOFF_RE.match(s):
            return s[:200]
    return sentences[0][:200]


def extract(email: RawEmail, category: Category) -> ExtractedFields:
    body = email.body
    signature = _signature_block(body)
    sig_text = "\n".join(signature)

    # Name: the From header is the most reliable source; signature second.
    name = email.sender_name or (signature[0] if signature else None)
    if name and ("@" in name or len(name.split()) > 5):
        name = None

    # Phone: look in the signature first, so a number quoted in the body
    # (an order total, say) is not mistaken for a phone number.
    phone = None
    for text in (sig_text, body):
        for m in PHONE_RE.finditer(text):
            if re.fullmatch(r"20\d\d-\d\d-\d\d", m.group(1).strip()):
                continue  # an ISO date, not a phone number
            if 10 <= len(re.sub(r"\D", "", m.group(1))) <= 13:
                phone = _clean_phone(m.group(1))
                break
        if phone:
            break
    if phone is None:
        # A malformed number in the signature is still worth keeping, so the
        # validator can flag it instead of it silently disappearing.
        m = re.search(r"(?:phone|mobile|ph|tel)\s*[:.]?\s*(\+?[\d\s\-]{6,})", sig_text, re.I)
        if m:
            phone = _clean_phone(m.group(1))

    emails_in_body = EMAIL_RE.findall(body)
    links = list(dict.fromkeys(URL_RE.findall(body)))  # de-duplicate, keep order

    skills = [skill for skill, pat in SKILLS.items() if re.search(pat, body, re.IGNORECASE if skill != "R" else 0)]

    grad = GRAD_YEAR_RE.search(body)
    hours = HOURS_RE.search(body)
    order = ORDER_RE.search(f"{email.subject}\n{body}")
    budget = BUDGET_RE.search(body)

    return ExtractedFields(
        name=name or None,
        organisation=_organisation(email, signature),
        email=email.sender_email or (emails_in_body[0].lower() if emails_in_body else None),
        phone=phone,
        links=links,
        skills=skills if category in (Category.INTERNSHIP, Category.UNKNOWN) else [],
        graduation_year=int(grad.group(1)) if grad else None,
        hours_per_week=int(hours.group(1)) if hours else None,
        order_id=order.group(1).upper().replace(" ", "") if order else None,
        budget=budget.group(1).strip().rstrip(".,") if budget and category == Category.SALES_LEAD else None,
        request_summary=_summary(email) or None,
    )
