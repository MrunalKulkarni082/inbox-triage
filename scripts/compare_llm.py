"""Compare the rule-based classifier with a free open-source LLM.

Runs both on every labelled email (the 30-email sample inbox plus the 8 live
examples), waits politely for the free tier's rate limit, and writes:

    output/llm_comparison.csv    one row per email
    (summary printed to the console)

Run:  python scripts/compare_llm.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from triage import classifier, llm_classifier, parser  # noqa: E402

LIVE_EXPECTED = {  # same expectations as tests/test_live_examples.py
    "Internship enquiry (complete)": "internship", "Internship enquiry with problems": "internship",
    "Sales lead with budget": "sales_lead", "Support request with order ID": "support",
    "Support request missing order ID": "support", "Phishing email": "spam",
    "Vague email": "unknown", "Vendor pitch": "vendor",
}


def labelled_emails():
    with open(ROOT / "data" / "sample_labels.csv", encoding="utf-8") as fh:
        labels = {r["file"]: r["expected_category"] for r in csv.DictReader(fh)}
    for path in parser.load_inbox(ROOT / "data" / "sample_inbox"):
        yield "sample", parser.parse_file(path), labels[path.name]
    for ex in json.loads((ROOT / "data" / "live_examples.json").read_text(encoding="utf-8")):
        raw = parser.from_text(ex["sender_name"], ex["sender_email"], ex["subject"], ex["body"],
                               [a.strip() for a in ex["attachments"].split(",") if a.strip()], label=ex["title"])
        yield "live", raw, LIVE_EXPECTED[ex["title"]]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for source, raw, expected in labelled_emails():
        rules = classifier.classify(raw)
        for attempt in range(4):
            wait = llm_classifier.seconds_until_capacity()
            if wait:
                time.sleep(wait + 1)
            t0 = time.perf_counter()
            ai, note = llm_classifier.classify_with_llm(raw)
            if ai is not None:
                break
        secs = time.perf_counter() - t0
        row = {
            "source": source, "email": raw.source_file, "expected": expected,
            "rules": rules.category.value, "rules_conf": rules.confidence,
            "llm": ai.category.value if ai else "", "llm_conf": ai.confidence if ai else "",
            "llm_model": ai.method.removeprefix("llm:") if ai else "", "llm_seconds": round(secs, 1),
            "note": "" if ai else note,
        }
        rows.append(row)
        print(f"{source:6} {raw.source_file[:34]:34} expected={expected:10} rules={row['rules']:10} "
              f"llm={row['llm'] or 'FAILED':10} {row['llm_model']}")

    out = ROOT / "output" / "llm_comparison.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    answered = [r for r in rows if r["llm"]]
    print("\n=== Summary ===")
    for src in ("sample", "live", "all"):
        sel = [r for r in rows if src == "all" or r["source"] == src]
        ans = [r for r in sel if r["llm"]]
        print(f"{src:6}: {len(sel)} emails | rules correct {sum(r['rules'] == r['expected'] for r in sel)}/{len(sel)}"
              f" | LLM answered {len(ans)}, correct {sum(r['llm'] == r['expected'] for r in ans)}/{len(ans)}"
              f" | rules and LLM agree {sum(r['llm'] == r['rules'] for r in ans)}/{len(ans)}")
    if answered:
        times = sorted(r["llm_seconds"] for r in answered)
        print(f"LLM time per email: median {times[len(times) // 2]} s, max {times[-1]} s")
    print("Disagreements:")
    for r in answered:
        if r["llm"] != r["rules"]:
            print(f"  {r['email']}: expected {r['expected']}, rules {r['rules']}, LLM {r['llm']} ({r['llm_model']})")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
