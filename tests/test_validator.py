from triage.classifier import classify
from triage.extractor import extract
from triage.models import Category, Classification, ExtractedFields, Severity
from triage.validator import has_blocking_issue, validate


def _cls(cat):
    return Classification(category=cat, confidence=0.9)


def _issues(email, cat, fields=None, ctx=None):
    return validate(email, _cls(cat), fields or extract(email, cat), ctx)


def test_support_without_order_id_is_blocking(email_factory):
    issues = _issues(email_factory("The bot is not working since yesterday, please fix."), Category.SUPPORT)
    assert has_blocking_issue(issues)
    assert any(i.field == "order_id" and i.severity == Severity.ERROR for i in issues)


def test_past_graduation_year_is_a_warning(email_factory):
    issues = _issues(email_factory("I graduated in 2024 and want an internship. I know Python."), Category.INTERNSHIP)
    assert any(i.field == "graduation_year" and i.severity == Severity.WARNING for i in issues)


def test_graduation_year_compared_to_email_date_not_today(email_factory):
    # An email sent in 2026 saying "graduate in 2026" is fine, whenever the test runs.
    e = email_factory("Student, I will graduate in 2026. Python.", date="Mon, 05 Oct 2026 10:00:00 +0530")
    assert not any(i.field == "graduation_year" for i in _issues(e, Category.INTERNSHIP))


def test_short_indian_phone_is_flagged(email_factory):
    f = ExtractedFields(name="A", email="a@b.com", phone="+91987654321", skills=["Python"], graduation_year=2027)
    issues = validate(email_factory("Student looking for internship."), _cls(Category.INTERNSHIP), f)
    assert any(i.field == "phone" for i in issues)


def test_empty_body_is_blocking(email_factory):
    issues = _issues(email_factory(""), Category.UNKNOWN)
    assert any(i.field == "body" and i.severity == Severity.ERROR for i in issues)


def test_unknown_category_is_blocking(email_factory):
    e = email_factory("Are you free?")
    assert has_blocking_issue(validate(e, classify(e), extract(e, Category.UNKNOWN)))


def test_personal_mailbox_business_lead_is_info(email_factory):
    e = email_factory("We want a quote to automate our invoices.", sender="V <v@gmail.com>")
    issues = _issues(e, Category.SALES_LEAD)
    assert any(i.severity == Severity.INFO and "personal mailbox" in i.message for i in issues)


def test_complete_record_has_no_issues(email_factory):
    body = ("I am a student, I expect to graduate in 2027. I want an internship. Python, SQL.\n\n"
            "Best regards,\nAsha Kumar\nPhone: +91 98450 12345")
    assert _issues(email_factory(body, sender="Asha Kumar <asha@uni.ac.in>"), Category.INTERNSHIP) == []


def test_repeat_order_id_is_linked(email_factory):
    issues = _issues(email_factory("Still failing. ORD-20417"), Category.SUPPORT,
                     ctx={"order_ids_seen": {"ORD-20417": "13_first.eml"}})
    assert any("already raised" in i.message for i in issues)
