"""The copy-paste examples shown in the demo must behave as their descriptions say."""

import json

import pytest

from conftest import ROOT
from triage import parser, pipeline
from triage.storage import Store

EXAMPLES = json.loads((ROOT / "data" / "live_examples.json").read_text(encoding="utf-8"))

EXPECTED = {
    "Internship enquiry (complete)": ("internship", "ready_for_review"),
    "Internship enquiry with problems": ("internship", "ready_for_review"),
    "Sales lead with budget": ("sales_lead", "ready_for_review"),
    "Support request with order ID": ("support", "ready_for_review"),
    "Support request missing order ID": ("support", "needs_attention"),
    "Phishing email": ("spam", "discarded"),
    "Vague email": ("unknown", "needs_attention"),
    "Vendor pitch": ("vendor", "ready_for_review"),
}


def _run(ex):
    raw = parser.from_text(ex["sender_name"], ex["sender_email"], ex["subject"], ex["body"],
                           [a.strip() for a in ex["attachments"].split(",") if a.strip()])
    return pipeline.run_single(raw, Store(":memory:")).results[0]


@pytest.mark.parametrize("ex", EXAMPLES, ids=[e["title"] for e in EXAMPLES])
def test_example_category_and_outcome(ex):
    r = _run(ex)
    assert (r.classification.category.value, r.status.value) == EXPECTED[ex["title"]]


def test_problem_example_flags_phone_and_graduation_year():
    r = _run(next(e for e in EXAMPLES if e["title"] == "Internship enquiry with problems"))
    assert {i.field for i in r.issues} >= {"phone", "graduation_year"}


def test_typed_email_twice_is_a_duplicate():
    ex = EXAMPLES[0]
    store = Store(":memory:")
    for expected in ("ready_for_review", "duplicate"):
        raw = parser.from_text(ex["sender_name"], ex["sender_email"], ex["subject"], ex["body"])
        assert pipeline.run_single(raw, store).results[0].status.value == expected
