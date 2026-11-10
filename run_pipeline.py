"""Command-line entry point.

    python run_pipeline.py                      # process the sample inbox
    python run_pipeline.py --inbox path/to/eml  # process your own .eml folder
    python run_pipeline.py --ai                 # use Claude if ANTHROPIC_API_KEY is set
    python run_pipeline.py --open-llm uncertain # free open-source LLM for emails the rules are unsure of
    python run_pipeline.py --reset              # start with an empty database

Outputs (in ./output):
    triage.db              SQLite database with every record
    exceptions.csv         every validation issue, for a person to work through
    review_queue.csv       records waiting for approval, with draft replies
    run_report.json        summary of the run (counts, timings, failures)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from triage import pipeline
from triage.storage import Store

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inbox triage workflow")
    ap.add_argument("--inbox", type=Path, default=ROOT / "data" / "sample_inbox")
    ap.add_argument("--out", type=Path, default=ROOT / "output")
    ap.add_argument("--ai", action="store_true", help="use Claude for classification (falls back to rules)")
    ap.add_argument("--open-llm", choices=["off", "uncertain", "all"], default="off",
                    help="ask a free open-source LLM (no key needed): only about emails the rules are unsure of, "
                         "or about all of them (slow: free tier allows ~10 requests/minute)")
    ap.add_argument("--reset", action="store_true", help="delete the database first")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args.out.mkdir(parents=True, exist_ok=True)
    db_path = args.out / "triage.db"
    if args.reset and db_path.exists():
        db_path.unlink()

    store = Store(db_path)
    report = pipeline.run(args.inbox, store, use_ai=args.ai, open_llm=args.open_llm)

    # ---- console summary ---------------------------------------------------
    print(f"\nRun {report.run_id}  |  {report.total} emails  |  {report.new_records} new  |  "
          f"{report.duration_ms} ms  |  AI {'on' if report.ai_used else 'off'}\n")
    rows = [{
        "file": r.raw.source_file[:34],
        "category": r.classification.category.value,
        "conf": f"{r.classification.confidence:.0%}",
        "status": r.status.value,
        "issues": len(r.issues),
    } for r in report.results]
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nBy status:  ", report.by_status)
    print("By category:", report.by_category)
    print("Stage time (ms):", report.stage_timings_ms)
    if report.failures:
        print("\nFAILURES:", *report.failures, sep="\n  ")

    # ---- files for people ---------------------------------------------------
    pd.DataFrame([{
        "file": r.raw.source_file, "sender": r.raw.sender_email, "category": r.classification.category.value,
        "severity": i.severity.value, "field": i.field, "message": i.message,
    } for r in report.results for i in r.issues]).to_csv(args.out / "exceptions.csv", index=False)

    pd.DataFrame([{
        "file": r.raw.source_file, "sender": r.raw.sender_email, "subject": r.raw.subject,
        "category": r.classification.category.value, "confidence": r.classification.confidence,
        "status": r.status.value, "draft_reply": r.draft_reply,
    } for r in report.results if r.draft_reply]).to_csv(args.out / "review_queue.csv", index=False)

    (args.out / "run_report.json").write_text(
        json.dumps(report.model_dump(mode="json", exclude={"results"}), indent=2), encoding="utf-8"
    )
    print(f"\nWrote output to {args.out}")
    store.close()
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
