"""Streamlit demo: run the workflow in a browser and inspect every step.

    streamlit run app.py
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from triage import ai_classifier, parser, pipeline
from triage.models import Status
from triage.storage import Store

ROOT = Path(__file__).resolve().parent
SAMPLE_INBOX = ROOT / "data" / "sample_inbox"
LABELS = ROOT / "data" / "sample_labels.csv"

st.set_page_config(page_title="Inbox Triage Workflow", page_icon="📥", layout="wide")

STATUS_LABEL = {
    "ready_for_review": "✅ Ready for review",
    "needs_attention": "⚠️ Needs attention",
    "duplicate": "🔁 Duplicate",
    "discarded": "🗑️ Discarded (spam)",
}
SEVERITY_ICON = {"error": "🔴", "warning": "🟠", "info": "🔵"}


# ---- session state ---------------------------------------------------------
def get_store() -> Store:
    if "store" not in st.session_state:
        tmp = Path(tempfile.gettempdir()) / f"triage_{id(st.session_state)}.db"
        tmp.unlink(missing_ok=True)
        st.session_state.store = Store(tmp)
        st.session_state.db_path = tmp
    return st.session_state.store


def reset():
    if "store" in st.session_state:
        st.session_state.store.close()
        Path(st.session_state.db_path).unlink(missing_ok=True)
        del st.session_state["store"]
    for key in ("report", "reports", "decisions"):
        st.session_state.pop(key, None)


st.session_state.setdefault("reports", [])
st.session_state.setdefault("decisions", {})

# ---- sidebar ---------------------------------------------------------------
LIVE_MODE = "✍️ Check one email live"
INBOX_MODE = "📥 Process a whole inbox"

with st.sidebar:
    mode = st.radio("Mode", [LIVE_MODE, INBOX_MODE])
    st.divider()
    run_clicked = False
    source, uploads = "", None
    if mode == INBOX_MODE:
        st.header("Run the workflow")
        source = st.radio("Inbox", ["Sample inbox (30 emails)", "Upload my own .eml files"])
        if source.startswith("Upload"):
            uploads = st.file_uploader("Drop .eml files", type=["eml"], accept_multiple_files=True)
            st.caption("Files are processed in memory for this session only.")

    st.markdown("**🤖 Open-source AI second opinion**")
    if mode == LIVE_MODE:
        llm_on = st.toggle("Ask a free open-source LLM too", value=True,
                           help="gpt-oss-120b and other open-weight models on OVHcloud's free, "
                                "no-key tier. If it fails or is busy, the rules answer stands.")
        open_llm = "all" if llm_on else "off"
    else:
        llm_on = st.toggle("Ask the LLM about emails the rules are unsure of", value=False,
                           help="Only 'unknown' emails are sent, which keeps within the free "
                                "limit of roughly 10 requests per minute.")
        open_llm = "uncertain" if llm_on else "off"
    st.caption("Free, no API key: open-weight models (gpt-oss, Llama, Mistral, Qwen) on "
               "OVHcloud AI Endpoints. The email text is sent to that server, so don't paste "
               "confidential emails.")

    ai_ready = ai_classifier.is_available()
    use_ai = False
    if ai_ready:  # only shown when an Anthropic key is configured on the machine
        use_ai = st.toggle("Use Claude instead of rules", value=False)

    if mode == INBOX_MODE:
        run_clicked = st.button("▶ Run workflow", type="primary", width="stretch")
    st.button("Reset database", on_click=reset, width="stretch")
    st.divider()
    st.caption("Tip: run the same email or inbox twice. The second time it is recognised "
               "as already processed and no duplicate record is created.")

if run_clicked:
    store = get_store()
    if source.startswith("Upload"):
        if not uploads:
            st.sidebar.error("Upload at least one .eml file first.")
            st.stop()
        folder = Path(tempfile.mkdtemp(prefix="triage_upload_"))
        for f in uploads:
            (folder / Path(f.name).name).write_bytes(f.getvalue())
        inbox = folder
    else:
        inbox = SAMPLE_INBOX
    with st.spinner("Processing inbox..."):
        st.session_state.report = pipeline.run(inbox, store, use_ai=use_ai, open_llm=open_llm)
        st.session_state.reports.append(st.session_state.report)
        st.session_state.inbox_is_sample = inbox == SAMPLE_INBOX

# ---- header ----------------------------------------------------------------
st.title("📥 Inbox Triage Workflow")
st.markdown(
    "Turns a messy shared inbox into **clean, validated records** and **ready-to-approve "
    "draft replies**. Every decision comes with a confidence score and a reason. "
    "Nothing is sent without a person approving it."
)
st.graphviz_chart(
    """
    digraph {
      rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2ff", fontname="Helvetica", fontsize=11];
      edge [color="#64748b"];
      in [label="Inbox\\n(.eml files)", fillcolor="#f1f5f9"];
      p [label="1. Parse"]; c [label="2. Classify\\nrules / AI"]; x [label="3. Extract\\nfields"];
      v [label="4. Validate\\n+ de-duplicate"]; s [label="5. Store\\nSQLite"]; d [label="6. Draft\\nreply"];
      h [label="7. Human\\napproves", fillcolor="#dcfce7"]; e [label="Exceptions\\nreport", fillcolor="#fee2e2"];
      in -> p -> c -> x -> v -> s -> d -> h; v -> e [style=dashed];
    }
    """
)

def show_trace(r) -> None:
    """Show one processed email stage by stage."""
    st.markdown("#### 1 · Parse")
    st.json({"from": f"{r.raw.sender_name} <{r.raw.sender_email}>", "subject": r.raw.subject,
             "received_at": str(r.raw.received_at), "attachments": r.raw.attachments,
             "fingerprint": r.raw.fingerprint[:16] + "…"}, expanded=True)
    with st.expander("Body text as parsed"):
        st.text(r.raw.body or "(empty)")

    st.markdown("#### 2 · Classify")
    c = r.classification
    if r.ai_note:
        rc, ac = r.rules_classification, r.ai_classification
        left, right = st.columns(2)
        with left:
            st.markdown("**📏 Rules** (instant, explainable)")
            st.markdown(f"`{rc.category.value}` · {rc.confidence:.0%}")
        with right:
            st.markdown("**🤖 Open-source LLM**")
            if ac:
                st.markdown(f"`{ac.category.value}` · {ac.confidence:.0%} · `{ac.method.removeprefix('llm:')}`")
                for reason in ac.reasons:
                    st.caption(f"• {reason}")
            st.caption(r.ai_note)
        if ac is None:
            st.warning("No AI answer this time, so the rules decided. That is the fallback working as designed.")
        elif ac.category == rc.category:
            st.success(f"Rules and AI agree: **{ac.category.value}**.")
        elif rc.category.value == "unknown":
            st.info(f"The rules were unsure; the AI's answer **{ac.category.value}** was used.")
        elif ac.confidence < 0.6:
            st.info("The AI was not confident enough, so the rules decided.")
        else:
            st.error("Rules and AI disagree, so the email is sent to a person to decide.")
        st.markdown("**Final decision**")
    st.markdown(f"**{c.category.value}** with **{c.confidence:.0%}** confidence (method: `{c.method}`)")
    if c.scores:
        st.bar_chart(pd.Series(c.scores, name="signal score"), horizontal=True)
    st.markdown("**Why:**\n" + ("\n".join(f"- {x}" for x in c.reasons) if c.reasons else "—"))
    st.caption("Confidence = winning score ÷ (all scores + 2). Below 55% the email is marked "
               "'unknown' and sent to a person.")

    st.markdown("#### 3 · Extract")
    st.json({k: v for k, v in r.fields.model_dump().items() if v not in (None, [], "")} or {"(nothing found)": None},
            expanded=True)

    st.markdown("#### 4 · Validate")
    if r.issues:
        for i in r.issues:
            st.markdown(f"{SEVERITY_ICON[i.severity.value]} **{i.severity.value}** · `{i.field}` — {i.message}")
    else:
        st.success("No issues found.")

    st.markdown("#### 5 · Route")
    st.markdown(f"Outcome: **{STATUS_LABEL[r.status.value]}**")

    st.markdown("#### 6 · Draft reply (waits for a person to approve)")
    if r.draft_reply:
        st.code(r.draft_reply, language=None)
    else:
        st.caption("No draft: spam and duplicates are not replied to.")


# ---- live mode: type or paste one email ------------------------------------
FIELDS = ("live_name", "live_email", "live_subject", "live_attach", "live_body")
EXAMPLES = json.loads((ROOT / "data" / "live_examples.json").read_text(encoding="utf-8"))


def load_example(ex: dict) -> None:
    st.session_state.update({"live_name": ex["sender_name"], "live_email": ex["sender_email"],
                             "live_subject": ex["subject"], "live_attach": ex["attachments"],
                             "live_body": ex["body"]})
    st.session_state.pop("live_result", None)


def clear_form() -> None:
    for k in FIELDS:
        st.session_state[k] = ""
    st.session_state.pop("live_result", None)


if mode == LIVE_MODE:
    for k in FIELDS:
        st.session_state.setdefault(k, "")
    st.subheader("Check one email live")
    st.markdown("Type or paste any email below, or load one of the examples, then press **Check this email**. "
                "It goes through exactly the same pipeline as a full inbox.")

    form_col, ex_col = st.columns([3, 2], gap="large")
    with ex_col:
        st.markdown("**Examples to try**")
        st.caption("New emails, not part of the 30-email sample set the rules were tuned on.")
        titles = [e["title"] for e in EXAMPLES]
        pick = st.selectbox("Example", titles, label_visibility="collapsed")
        ex = EXAMPLES[titles.index(pick)]
        st.button("⬅ Load into the form", on_click=load_example, args=(ex,), width="stretch")
        st.markdown(f"*What it shows:* {ex['shows']}")
        st.caption("Or copy the text (icon at the top right of the box) and paste or edit it yourself:")
        st.code(f"From: {ex['sender_name']} <{ex['sender_email']}>\nSubject: {ex['subject']}\n\n{ex['body']}",
                language=None, wrap_lines=True)

    with form_col:
        a, b = st.columns(2)
        a.text_input("Sender name", key="live_name", placeholder="Asha Kumar")
        b.text_input("Sender email", key="live_email", placeholder="asha@example.com")
        st.text_input("Subject", key="live_subject", placeholder="Internship enquiry")
        st.text_area("Email body", key="live_body", height=280,
                     placeholder="Hello,\n\nI am a final-year student looking for an internship...")
        st.text_input("Attachment file names (optional, comma-separated)", key="live_attach",
                      placeholder="My_CV.pdf")
        c1, c2 = st.columns([2, 1])
        check = c1.button("▶ Check this email", type="primary", width="stretch")
        c2.button("Clear", on_click=clear_form, width="stretch")

    if check:
        body, subject = st.session_state.live_body.strip(), st.session_state.live_subject.strip()
        sender = st.session_state.live_email.strip()
        if not body and not subject:
            st.error("Enter at least a subject or a body.")
        elif sender and "@" not in sender:
            st.error("The sender email needs an @.")
        else:
            raw = parser.from_text(
                st.session_state.live_name.strip(), sender or "unknown@unknown.invalid", subject, body,
                [x.strip() for x in st.session_state.live_attach.split(",") if x.strip()],
            )
            with st.spinner("Checking..." + (" (asking the open-source LLM, usually 2-10 s)" if open_llm != "off" else "")):
                rep = pipeline.run_single(raw, get_store(), use_ai=use_ai, open_llm=open_llm)
            if rep.failures:
                st.error("Could not process this email: " + "; ".join(rep.failures))
            else:
                st.session_state.live_result = (rep.results[0], rep.duration_ms)

    if "live_result" in st.session_state:
        r, ms = st.session_state.live_result
        st.divider()
        st.markdown(f"### Result: {STATUS_LABEL[r.status.value]} · **{r.classification.category.value}** "
                    f"({r.classification.confidence:.0%}) · {len(r.issues)} issue(s) · {ms} ms")
        if r.status == Status.DUPLICATE:
            st.info("This exact email was already processed in this session, so no new record was created. "
                    "Change any word to make it a new email.")
        show_trace(r)
    st.stop()


# ---- inbox mode ------------------------------------------------------------
report = st.session_state.get("report")
if report is None:
    st.info("Choose an inbox in the sidebar and press **Run workflow** to start.")
    st.stop()

if report.failures:
    st.error("Some files could not be processed:\n\n" + "\n".join(f"- {f}" for f in report.failures))

# ---- headline metrics --------------------------------------------------------
m = st.columns(6)
m[0].metric("Emails processed", report.total)
m[1].metric("New records", report.new_records)
m[2].metric("Ready for review", report.by_status.get("ready_for_review", 0))
m[3].metric("Needs attention", report.by_status.get("needs_attention", 0))
m[4].metric("Duplicates / spam", report.by_status.get("duplicate", 0) + report.by_status.get("discarded", 0))
m[5].metric("Run time", f"{report.duration_ms} ms")

tabs = st.tabs(["Overview", "Review queue", "Step-by-step inspector", "Exceptions",
                "Accuracy", "Database (SQL)", "Run log"])

# ---- Overview ----------------------------------------------------------------
with tabs[0]:
    left, right = st.columns(2)
    with left:
        st.subheader("By category")
        st.bar_chart(pd.Series(report.by_category, name="emails").sort_values(ascending=False), horizontal=True)
    with right:
        st.subheader("By outcome")
        st.bar_chart(pd.Series({STATUS_LABEL[k]: v for k, v in report.by_status.items()}, name="emails"),
                     horizontal=True)
    st.subheader("All emails")
    st.dataframe(pd.DataFrame([{
        "file": r.raw.source_file,
        "from": r.raw.sender_email,
        "subject": r.raw.subject,
        "category": r.classification.category.value,
        "confidence": r.classification.confidence,
        "method": r.classification.method,
        "outcome": STATUS_LABEL[r.status.value],
        "issues": len(r.issues),
    } for r in report.results]), width="stretch", hide_index=True,
        column_config={"confidence": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f")})

# ---- Review queue --------------------------------------------------------------
with tabs[1]:
    st.markdown("Drafts wait here for a person. **Approve**, **edit then approve**, or **reject**. "
                "Decisions are saved to the `reviews` table.")
    queue = [r for r in report.results if r.draft_reply]
    filt = st.radio("Show", ["All", "Ready for review", "Needs attention"], horizontal=True)
    if filt == "Ready for review":
        queue = [r for r in queue if r.status == Status.READY_FOR_REVIEW]
    elif filt == "Needs attention":
        queue = [r for r in queue if r.status == Status.NEEDS_ATTENTION]

    for r in queue:
        fp = r.raw.fingerprint
        decided = st.session_state.decisions.get(fp)
        label = (f"{STATUS_LABEL[r.status.value]} · {r.classification.category.value} · "
                 f"{r.raw.sender_name or r.raw.sender_email} — {r.raw.subject}")
        if decided:
            label = f"[{decided.upper()}] " + label
        with st.expander(label):
            a, b = st.columns(2)
            with a:
                st.markdown("**Original email**")
                st.text(r.raw.body[:1500] or "(empty)")
                if r.issues:
                    st.markdown("**Issues found**")
                    for i in r.issues:
                        st.markdown(f"{SEVERITY_ICON[i.severity.value]} `{i.field}` — {i.message}")
            with b:
                st.markdown("**Draft reply**")
                text = st.text_area("Draft", r.draft_reply, height=320, key=f"draft_{fp}",
                                    label_visibility="collapsed")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"ok_{fp}", type="primary", disabled=bool(decided)):
                    decision = "approved" if text == r.draft_reply else "edited"
                    get_store().record_review(fp, decision, text)
                    st.session_state.decisions[fp] = decision
                    st.rerun()
                if c2.button("Reject", key=f"no_{fp}", disabled=bool(decided)):
                    get_store().record_review(fp, "rejected", None)
                    st.session_state.decisions[fp] = "rejected"
                    st.rerun()

# ---- Inspector -----------------------------------------------------------------
with tabs[2]:
    st.markdown("Pick one email and follow it through every stage of the pipeline.")
    names = [r.raw.source_file for r in report.results]
    pick = st.selectbox("Email", names)
    r = next(x for x in report.results if x.raw.source_file == pick)

    show_trace(r)

# ---- Exceptions --------------------------------------------------------------------
with tabs[3]:
    rows = [{"severity": f"{SEVERITY_ICON[i.severity.value]} {i.severity.value}", "file": r.raw.source_file,
             "category": r.classification.category.value, "field": i.field, "message": i.message}
            for r in report.results for i in r.issues]
    if rows:
        df = pd.DataFrame(rows)
        order = {"🔴 error": 0, "🟠 warning": 1, "🔵 info": 2}
        df = df.sort_values("severity", key=lambda s: s.map(order))
        counts = df["severity"].value_counts()
        st.markdown(" · ".join(f"{k}: **{v}**" for k, v in counts.items()))
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button("Download exceptions.csv", df.to_csv(index=False), "exceptions.csv", "text/csv")
    else:
        st.success("No issues in this run.")

# ---- Accuracy ------------------------------------------------------------------------
with tabs[4]:
    if not st.session_state.get("inbox_is_sample"):
        st.info("Accuracy is measured against hand-labelled answers, which exist only for the sample inbox.")
    else:
        with open(LABELS, encoding="utf-8") as fh:
            labels = {row["file"]: row for row in csv.DictReader(fh)}
        rows = []
        for r in report.results:
            lab = labels.get(r.raw.source_file)
            if not lab:
                continue
            rows.append({"file": r.raw.source_file, "expected": lab["expected_category"],
                         "predicted": r.classification.category.value,
                         "correct": lab["expected_category"] == r.classification.category.value,
                         "note": lab["note"]})
        df = pd.DataFrame(rows)
        if not len(df):
            st.info("No labelled emails in this run.")
        else:
            acc = df["correct"].mean()
            st.metric("Category accuracy on the labelled sample", f"{acc:.0%}", help="Hand-labelled answers in data/sample_labels.csv")
            st.markdown("**Confusion matrix** (rows = expected, columns = predicted)")
            st.dataframe(pd.crosstab(df["expected"], df["predicted"]), width="stretch")
            st.dataframe(df, width="stretch", hide_index=True)
            st.warning("Honest caveat: the rules were tuned on these same 30 emails, so this "
                       "number is optimistic. Real accuracy has to be measured on new, unseen mail.")

# ---- Database ----------------------------------------------------------------------
with tabs[5]:
    presets = {
        "Internship candidates with skills": "SELECT name, organisation, graduation_year, hours_per_week, skills\nFROM emails WHERE category = 'internship' ORDER BY graduation_year",
        "Open sales leads with budget": "SELECT name, organisation, budget, request_summary\nFROM emails WHERE category = 'sales_lead' AND status != 'duplicate'",
        "Issues by severity": "SELECT severity, COUNT(*) AS n FROM issues GROUP BY severity ORDER BY n DESC",
        "Emails per category and outcome": "SELECT category, status, COUNT(*) AS n FROM emails GROUP BY 1, 2 ORDER BY 1",
        "Review decisions": "SELECT e.subject, r.decision, r.reviewed_at FROM reviews r JOIN emails e USING (fingerprint)",
        "Run history": "SELECT run_id, total, new_records, issue_count, duration_ms FROM runs ORDER BY started_at",
    }
    choice = st.selectbox("Example query", list(presets))
    sql = st.text_area("SQL (read-only)", presets[choice], height=110)
    try:
        st.dataframe(pd.DataFrame(get_store().query(sql)), width="stretch", hide_index=True)
    except Exception as exc:  # show SQL errors to the user, don't crash the app
        st.error(str(exc))

# ---- Run log -----------------------------------------------------------------------------
with tabs[6]:
    st.subheader("This run")
    st.json(json.loads(report.model_dump_json(exclude={"results"})), expanded=False)
    st.subheader("Time per stage (ms)")
    st.bar_chart(pd.Series(report.stage_timings_ms, name="ms"))
    st.subheader("All runs this session")
    st.dataframe(pd.DataFrame([{"run_id": x.run_id, "emails": x.total, "new": x.new_records,
                                "issues": x.issue_count, "ms": x.duration_ms, "ai": x.ai_used}
                               for x in st.session_state.reports]), hide_index=True, width="stretch")
