"""End-to-end tests: the whole workflow on the sample inbox."""

import csv
import shutil

import pytest

from conftest import INBOX, LABELS
from triage import ai_classifier, parser, pipeline
from triage.models import Category, Classification
from triage.storage import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture(scope="module")
def labels():
    with open(LABELS, encoding="utf-8") as fh:
        return {row["file"]: row for row in csv.DictReader(fh)}


def test_whole_inbox_runs_without_failures(store):
    report = pipeline.run(INBOX, store)
    assert report.failures == []
    assert report.total == 30


def test_categories_match_labels(store, labels):
    report = pipeline.run(INBOX, store)
    wrong = [(r.raw.source_file, r.classification.category.value) for r in report.results
             if r.classification.category.value != labels[r.raw.source_file]["expected_category"]]
    assert wrong == []


def test_statuses_match_labels(store, labels):
    report = pipeline.run(INBOX, store)
    wrong = [(r.raw.source_file, r.status.value) for r in report.results
             if r.status.value != labels[r.raw.source_file]["expected_status"]]
    assert wrong == []


def test_rerun_is_idempotent(store):
    first = pipeline.run(INBOX, store)
    second = pipeline.run(INBOX, store)
    assert first.new_records == 29  # 30 files, one is an exact duplicate
    assert second.new_records == 0  # nothing new the second time
    assert second.by_status == {"duplicate": 30}
    assert store.query("SELECT COUNT(*) AS n FROM emails")[0]["n"] == 29


def test_spam_and_duplicates_get_no_draft(store):
    for r in pipeline.run(INBOX, store).results:
        if r.status.value in ("discarded", "duplicate"):
            assert r.draft_reply is None


def test_broken_file_does_not_stop_the_run(store, tmp_path, monkeypatch):
    shutil.copy(INBOX / "01_internship_complete.eml", tmp_path / "a.eml")
    (tmp_path / "b.eml").write_bytes(b"corrupt")
    shutil.copy(INBOX / "13_support_with_order.eml", tmp_path / "c.eml")
    real = parser.parse_file

    def flaky(path):
        if path.name == "b.eml":
            raise ValueError("corrupt file")
        return real(path)

    monkeypatch.setattr(parser, "parse_file", flaky)
    report = pipeline.run(tmp_path, store)
    assert report.total == 2
    assert len(report.failures) == 1 and "b.eml" in report.failures[0]


def test_issues_saved_with_every_severity(store):
    pipeline.run(INBOX, store)
    rows = store.query("SELECT severity, COUNT(*) AS n FROM issues GROUP BY severity")
    assert {r["severity"] for r in rows} == {"error", "warning", "info"}


def test_store_query_is_read_only(store):
    with pytest.raises(ValueError):
        store.query("DELETE FROM emails")


# ---- optional AI step: no real API calls are made in tests -----------------

def test_ai_off_without_key(store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    report = pipeline.run(INBOX, store, use_ai=True)
    assert report.ai_used is False
    assert all(r.classification.method == "rules" for r in report.results)


def test_ai_result_used_when_available(store, monkeypatch):
    monkeypatch.setattr(ai_classifier, "is_available", lambda: True)
    monkeypatch.setattr(ai_classifier, "classify_with_ai",
                        lambda e: Classification(category=Category.VENDOR, confidence=0.9, reasons=["t"], method="ai"))
    report = pipeline.run(INBOX, store, use_ai=True)
    assert report.ai_used and all(r.classification.method == "ai" for r in report.results)


def test_ai_failure_falls_back_to_rules(store, monkeypatch):
    monkeypatch.setattr(ai_classifier, "is_available", lambda: True)
    monkeypatch.setattr(ai_classifier, "classify_with_ai", lambda e: None)  # every call "fails"
    report = pipeline.run(INBOX, store, use_ai=True)
    assert report.failures == []
    assert all(r.classification.method == "rules" for r in report.results)


def test_ai_disagreement_is_recorded(store, monkeypatch):
    monkeypatch.setattr(ai_classifier, "is_available", lambda: True)
    monkeypatch.setattr(ai_classifier, "classify_with_ai",
                        lambda e: Classification(category=Category.SPAM, confidence=0.95, reasons=["ai"], method="ai"))
    first = pipeline.run(INBOX, store, use_ai=True).results[0]  # an internship email
    assert any("rules said 'internship'" in r for r in first.classification.reasons)
