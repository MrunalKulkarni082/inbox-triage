from triage.drafter import draft, first_name
from triage.models import Category, ExtractedFields, Severity, ValidationIssue


def test_first_name_variants():
    assert first_name("Ananya Rao") == "Ananya"
    assert first_name("Dr. Sana Qureshi") == "Dr. Qureshi"
    assert first_name("Mr Rahul Verma") == "Rahul"
    assert first_name(None) == "[confirm name]"
    assert first_name("Digital Growth Team") == "there"


def test_internship_draft_asks_for_missing_details(email_factory):
    f = ExtractedFields(name="Rohit Menon", skills=["Python"])
    issues = [ValidationIssue(field="graduation_year", severity=Severity.WARNING, message="x"),
              ValidationIssue(field="phone", severity=Severity.WARNING, message="x")]
    text = draft(email_factory("internship please"), Category.INTERNSHIP, f, issues)
    assert text.startswith("Hi Rohit,")
    assert "expected graduation date" in text
    assert "phone number" in text
    assert "hours a week" in text  # not given, so the reply asks


def test_draft_does_not_ask_for_what_we_have(email_factory):
    f = ExtractedFields(name="A B", skills=["SQL"], hours_per_week=15, graduation_year=2027, phone="+919999999999")
    text = draft(email_factory("x"), Category.INTERNSHIP, f, [])
    assert "hours a week" not in text
    assert "graduation date" not in text


def test_spam_gets_no_draft(email_factory):
    assert draft(email_factory("x"), Category.SPAM, ExtractedFields(), []) is None


def test_support_draft_uses_order_id(email_factory):
    text = draft(email_factory("x"), Category.SUPPORT, ExtractedFields(name="Farah Ali", order_id="ORD-1"), [])
    assert "ORD-1" in text


def test_every_category_template_renders(email_factory):
    for cat in (Category.INTERNSHIP, Category.SALES_LEAD, Category.SUPPORT, Category.VENDOR, Category.UNKNOWN):
        assert draft(email_factory("x"), cat, ExtractedFields(), [])
