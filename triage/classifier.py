"""Stage 2 - Classify (rule-based, the default).

Each category has a list of weighted *signals*: patterns that suggest an email
belongs to it. We add up the weights of every signal that fires, then turn
the scores into a confidence value.

Why rules and not only AI?
  * Free, fast, works offline, and gives the same answer every time.
  * Every decision can be explained: the reasons list shows exactly which
    signals fired.
  * It is the safety net when the optional AI step is off or fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Category, Classification, RawEmail

# Below this confidence the email is labelled UNKNOWN and sent to a person.
CONFIDENCE_THRESHOLD = 0.55

# Smoothing term: stops a single weak signal producing high confidence.
# With SMOOTHING = 2, one signal of weight 2 gives 2 / (2 + 2) = 0.50 -> unknown.
SMOOTHING = 2.0


@dataclass(frozen=True)
class Signal:
    label: str           # human-readable reason shown in the UI
    pattern: re.Pattern  # what to look for
    weight: float        # how strongly it points to the category
    where: str = "text"  # "text" (subject + body), "sender", or "attachments"


def _s(label: str, regex: str, weight: float, where: str = "text") -> Signal:
    return Signal(label, re.compile(regex, re.IGNORECASE), weight, where)


SIGNALS: dict[Category, list[Signal]] = {
    Category.INTERNSHIP: [
        _s("mentions 'internship' / 'intern'", r"\bintern(ship)?s?\b", 3.0),
        _s("mentions CV / resume", r"\b(cv|resume|résumé)\b", 2.0),
        _s("student / degree language", r"\b(b\.?tech|bs-?ms|m\.?sc|b\.?sc|undergrad\w*|master'?s|final[- ]year|student|semester)\b", 1.5),
        _s("graduation year mentioned", r"\bgraduat\w*\b.{0,30}\b20\d\d\b|\bclass of 20\d\d\b", 1.5),
        _s("asks about openings / opportunities", r"\b(opening|opportunit\w+|position|role)s?\b", 1.0),
        _s("academic email domain", r"\.(ac\.in|edu|ac\.uk|edu\.in)$", 2.0, "sender"),
        _s("CV-like attachment", r"(cv|resume)", 2.0, "attachments"),
    ],
    Category.SALES_LEAD: [
        _s("asks for a quote / pricing", r"\b(quote|quotation|pricing|price|cost estimate|proposal)\b", 3.0),
        _s("wants to automate their process", r"\bautomat\w+\b.{0,40}\b(our|my|we)\b|\b(our|we)\b.{0,40}\bautomat\w+", 2.0),
        _s("mentions budget", r"\bbudget\b|₹\s?\d|\b\d+\s?lakhs?\b", 2.0),
        _s("asks for a call / demo", r"\b(demo|discovery call|schedule a call|book a call|meeting)\b", 1.5),
        _s("describes their business", r"\b(our (company|team|business|firm|clinic|store)|we are a)\b", 1.5),
        _s("mentions a timeline", r"\b(by (q[1-4]|next month|january|february|march|april|may|june|july|august|september|october|november|december))\b", 1.0),
    ],
    Category.SUPPORT: [
        _s("reports something broken", r"\b(not working|broken|error|bug|crash\w*|fail\w*|stopped|issue)\b", 3.0),
        _s("asks for help / urgent", r"\b(urgent|asap|help|please fix|support)\b", 1.5),
        _s("mentions an order / ticket ID", r"\b(ord|inv|tkt|ticket)[- #]?\d{3,}\b|#\d{4,}", 2.0),
        _s("existing customer language", r"\b(your (tool|system|workflow|bot|integration)|we (bought|purchased|use)|since (the|your) (update|deployment))\b", 2.0),
        _s("refund / cancel", r"\b(refund|cancel\w*|downtime)\b", 1.5),
    ],
    Category.VENDOR: [
        _s("offers a service", r"\b(we offer|we provide|our services|our agency|outsourc\w+)\b", 2.5),
        _s("partnership pitch", r"\b(partner(ship)?|collaborat\w+|reseller)\b", 1.5),
        _s("white-label / agency language", r"\b(white[- ]label|development agency|seo agency|\d+-person (agency|team))\b", 2.0),
        _s("SEO / marketing pitch", r"\b(seo|lead generation|backlinks|marketing services|rank\w* on google)\b", 3.0),
        _s("rate card / discount offer", r"\b(rate card|special (offer|discount)|per hour|hourly rate)\b", 1.5),
    ],
    Category.SPAM: [
        _s("prize / lottery language", r"\b(winner|won|lottery|jackpot|prize|congratulations)\b", 3.0),
        _s("pressure to click", r"\b(click (here|below|the link)|act now|limited time|claim (now|your))\b", 2.5),
        _s("crypto / money scheme", r"\b(crypto|bitcoin|investment opportunity|guaranteed returns|wire transfer)\b", 3.0),
        _s("asks for credentials", r"\b(verify your (account|password)|confirm your (bank|password)|otp)\b", 3.0),
        _s("many links", r"(https?://\S+.*){4,}", 1.5),
    ],
}


def _target_text(email: RawEmail, where: str) -> str:
    if where == "sender":
        return email.sender_email
    if where == "attachments":
        return " ".join(email.attachments)
    return f"{email.subject}\n{email.body}"


def score(email: RawEmail) -> tuple[dict[Category, float], dict[Category, list[str]]]:
    """Raw score and matched reasons for every category."""
    scores: dict[Category, float] = {}
    reasons: dict[Category, list[str]] = {}
    for category, signals in SIGNALS.items():
        total, hit = 0.0, []
        for sig in signals:
            if sig.pattern.search(_target_text(email, sig.where)):
                total += sig.weight
                hit.append(f"{sig.label} (+{sig.weight:g})")
        scores[category] = total
        reasons[category] = hit
    return scores, reasons


def classify(email: RawEmail) -> Classification:
    scores, reasons = score(email)
    best = max(scores, key=lambda c: scores[c])
    top = scores[best]
    total = sum(scores.values())

    # Share of the evidence that points to the winner, shrunk when there is
    # little evidence overall. Range 0..1.
    confidence = top / (total + SMOOTHING) if top > 0 else 0.0

    if confidence < CONFIDENCE_THRESHOLD:
        runner_up = sorted(scores, key=lambda c: scores[c], reverse=True)[1]
        why = [f"best guess '{best.value}' only {confidence:.0%} confident"]
        if scores[runner_up] > 0:
            why.append(f"competing signals for '{runner_up.value}'")
        if top == 0:
            why = ["no known signals matched"]
        return Classification(
            category=Category.UNKNOWN,
            confidence=round(confidence, 3),
            reasons=why + reasons[best],
            method="rules",
            scores={c.value: s for c, s in scores.items()},
        )

    return Classification(
        category=best,
        confidence=round(confidence, 3),
        reasons=reasons[best],
        method="rules",
        scores={c.value: s for c, s in scores.items()},
    )
