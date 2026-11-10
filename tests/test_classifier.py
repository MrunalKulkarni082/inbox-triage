import pytest

from triage.classifier import CONFIDENCE_THRESHOLD, classify
from triage.models import Category


def test_internship_with_strong_signals(email_factory):
    e = email_factory("I am a final-year student looking for an internship. CV attached. I expect to graduate in 2027.",
                      sender="A <a@college.ac.in>", attachments=("A_CV.pdf",))
    c = classify(e)
    assert c.category == Category.INTERNSHIP
    assert c.confidence >= 0.7
    assert any("internship" in r for r in c.reasons)  # the decision is explained


def test_sales_lead(email_factory):
    c = classify(email_factory("We are a small clinic and we want to automate our reminders. "
                               "Could you send a quote? Budget is 2 lakh."))
    assert c.category == Category.SALES_LEAD


def test_support(email_factory):
    c = classify(email_factory("The workflow is not working since your update. Order ORD-12345. Urgent."))
    assert c.category == Category.SUPPORT


def test_spam(email_factory):
    c = classify(email_factory("Congratulations, you are a winner of the lottery jackpot! Click here to claim now."))
    assert c.category == Category.SPAM


def test_no_signals_is_unknown_with_zero_confidence(email_factory):
    c = classify(email_factory("Are you free this week?"))
    assert c.category == Category.UNKNOWN
    assert c.confidence == 0.0
    assert c.reasons == ["no known signals matched"]


def test_single_weak_signal_is_not_enough(email_factory):
    c = classify(email_factory("Is there a role for me?"))
    assert c.category == Category.UNKNOWN
    assert c.confidence < CONFIDENCE_THRESHOLD


def test_mixed_signals_go_to_a_person(email_factory):
    # Half "sell us a workshop", half "internship": a person should decide.
    c = classify(email_factory("Our club would like a workshop for our students. Could you share pricing? "
                               "We are also interested in internship opportunities.", sender="s <s@gmail.com>"))
    assert c.category == Category.UNKNOWN


@pytest.mark.parametrize("cat", ["internship", "sales_lead", "support", "vendor", "spam"])
def test_scores_reported_for_every_category(email_factory, cat):
    assert cat in classify(email_factory("internship quote not working seo winner")).scores
