from triage.extractor import extract
from triage.models import Category

BODY = """Dear Team,

I am a student and I expect to graduate in 2027. I know Python, SQL, Power BI and Excel.
I can give 15 hours a week. Portfolio: https://example.com/me

Best regards,
Asha Kumar
Greenfield Institute of Technology
Phone: +91 98450 12345
"""


def test_internship_fields(email_factory):
    f = extract(email_factory(BODY, sender="Asha Kumar <asha@greenfield.ac.in>"), Category.INTERNSHIP)
    assert f.name == "Asha Kumar"
    assert f.organisation == "Greenfield Institute of Technology"
    assert f.phone == "+919845012345"
    assert f.graduation_year == 2027
    assert f.hours_per_week == 15
    assert f.skills == ["Python", "SQL", "Excel", "Power BI"]
    assert f.links == ["https://example.com/me"]


def test_bare_ten_digit_phone_gets_country_code(email_factory):
    assert extract(email_factory("Thanks,\nRavi\n9876543210"), Category.UNKNOWN).phone == "+919876543210"


def test_date_is_not_mistaken_for_phone(email_factory):
    assert extract(email_factory("The meeting is on 2026-10-05 at noon."), Category.UNKNOWN).phone is None


def test_order_id_from_subject(email_factory):
    f = extract(email_factory("It broke again.", subject="Problem with ORD-20417"), Category.SUPPORT)
    assert f.order_id == "ORD-20417"


def test_budget_only_for_sales(email_factory):
    body = "Our budget is ₹6 lakh for this project."
    assert extract(email_factory(body), Category.SALES_LEAD).budget == "₹6 lakh"
    assert extract(email_factory(body), Category.SUPPORT).budget is None


def test_missing_fields_stay_empty_not_guessed(email_factory):
    f = extract(email_factory("Hi, any internships?"), Category.INTERNSHIP)
    assert f.graduation_year is None
    assert f.hours_per_week is None
    assert f.phone is None


def test_organisation_from_title_line(email_factory):
    body = "We want a demo.\n\nBest,\nNeha\nOperations Lead, Urban Threads\n"
    f = extract(email_factory(body, sender="Neha <neha@urbanthreads.co.in>"), Category.SALES_LEAD)
    assert f.organisation == "Urban Threads"


def test_summary_picks_the_request(email_factory):
    body = "Hello,\n\nWe are a clinic with three sites. We want to automate our reminders. Thanks."
    assert extract(email_factory(body), Category.SALES_LEAD).request_summary == "We want to automate our reminders."
