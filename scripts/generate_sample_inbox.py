"""Generate the sample inbox used by the demo and the tests.

Every person, company and address here is fictional. The set is deliberately
messy: duplicates, HTML-only mail, missing details, malformed phone numbers,
ambiguous requests, spam and an empty email - the things a real inbox has.

Run:  python scripts/generate_sample_inbox.py
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_inbox"
IST = timezone(timedelta(hours=5, minutes=30))
BASE = datetime(2026, 10, 1, 9, 0, tzinfo=IST)

# (file stem, from name, from address, subject, body, attachments, html_only, hours offset)
EMAILS: list[tuple] = [
    ("01_internship_complete", "Ananya Rao", "ananya.rao@greenfield.ac.in",
     "Internship enquiry - data and automation",
     """Dear Team,

I am Ananya Rao, a final-year B.Tech student in Computer Science at Greenfield Institute of Technology. I expect to graduate in 2027.

I am looking for an internship in workflow automation. I work with Python, SQL and Excel, and I have built small automations with Zapier and n8n. I can give 15 hours a week remotely.

Please find my CV attached. I would be glad to talk about where I could help.

Best regards,
Ananya Rao
Greenfield Institute of Technology
Phone: +91 98450 12345
https://github.com/ananya-rao-demo
""", ["Ananya_Rao_CV.pdf"], False, 0),

    ("02_internship_gmail_sparse", "Rohit Menon", "rohit.menon.dev@gmail.com",
     "Looking for an internship",
     """Hi,

I am a student interested in an internship at your company. I know Python and Power BI. Do you have any openings?

Thanks,
Rohit
""", [], False, 3),

    ("03_internship_past_grad", "Priya Shah", "priya.shah@lakeview.edu",
     "Internship / junior role opportunity",
     """Hello,

I graduated in 2024 with a B.Sc in Statistics from Lakeview University and I am looking for an internship or junior role in data and automation. I use Python, R, SQL and Tableau. I have attached my resume.

I can give 25 hours a week.

Kind regards,
Priya Shah
Lakeview University
Mobile: +91 99001 22334
""", ["Priya_Shah_Resume.pdf"], False, 5),

    ("04_internship_html_only", "Karan Gill", "karan.gill@nsis.ac.in",
     "Internship application",
     """<html><body><p>Dear Hiring Team,</p>
<p>I am a <b>master's student</b> at the National School of Inference Sciences and would like to apply for an <b>internship</b>. I expect to graduate in 2027.</p>
<p>Skills: Python, Pandas, SQL, Machine Learning, Docker.</p>
<p>I can commit 20 hours per week. My CV is attached.</p>
<p>Regards,<br>Karan Gill<br>Phone: +91 91234 56789</p></body></html>""",
     ["Karan_Gill_CV.pdf"], True, 8),

    # Exact resend of 01 - must be caught as a duplicate.
    ("05_internship_duplicate_resend", "Ananya Rao", "ananya.rao@greenfield.ac.in",
     "Internship enquiry - data and automation",
     None, ["Ananya_Rao_CV.pdf"], False, 26),

    ("06_internship_followup", "Rohit Menon", "rohit.menon.dev@gmail.com",
     "Re: Looking for an internship",
     """Hi again,

Following up on my earlier email about an internship. I forgot to mention I graduate in 2026 and can give 10 hours a week. I have attached my CV.

Thanks,
Rohit Menon
""", ["Rohit_CV.pdf"], False, 30),

    ("07_internship_bad_phone", "Meera Iyer", "meera.iyer@greenfield.ac.in",
     "Summer internship - Python / SQL",
     """Dear Sir/Madam,

I am a third-year student at Greenfield Institute of Technology looking for a summer internship. I expect to graduate in 2028. I am comfortable with Python, SQL and Excel.

Best regards,
Meera Iyer
Phone: +91 98765 4321
""", [], False, 33),

    ("08_internship_two_addresses", "Arjun Nair", "arjun.nair@nsis.ac.in",
     "Internship - automation and data",
     """Hello Team,

I am a BS-MS student at the National School of Inference Sciences, graduating in 2027. I would like to explore an internship in AI and workflow automation. I work with Python, SQL, Stata and Power BI, and can start remotely with about 12 hours a week.

My CV is attached. Please reply to my personal address arjun.nair.personal@gmail.com as my institute mail expires soon.

Best regards,
Arjun Nair
Mobile: +91 90000 11122
""", ["Arjun_Nair_CV.pdf"], False, 40),

    ("09_sales_clinic", "Dr. Sana Qureshi", "sana@sunrise-clinic.in",
     "Automating appointment reminders - quote?",
     """Hello,

We are a family clinic with three locations. Our staff spend about two hours a day calling patients to remind them about appointments, and we want to automate this using WhatsApp or SMS.

Could you send a quote? Our budget is around ₹2 lakh and we would like it running by January.

Regards,
Dr. Sana Qureshi
Sunrise Family Clinic
Phone: +91 98111 22233
""", [], False, 44),

    ("10_sales_logistics_freemail", "Vikram Joshi", "vikram.swiftcargo@gmail.com",
     "Invoice processing automation",
     """Hi,

Our company handles about 900 supplier invoices a month and we key them into Tally by hand. We want to automate our invoice processing. Can we schedule a call to discuss pricing?

Thanks,
Vikram Joshi
SwiftCargo Logistics Pvt Ltd
+91 97654 32100
""", [], False, 50),

    ("11_sales_retail_demo", "Neha Kapoor", "neha@urbanthreads.co.in",
     "Demo request - order and inventory sync",
     """Hi there,

We are a clothing brand selling on Shopify and Amazon. Inventory gets out of sync between the two and we oversell every week. We would like to automate our stock updates.

Could we book a demo and get a rough cost estimate? Budget is flexible, roughly $5,000.

Best,
Neha Kapoor
Operations Lead, Urban Threads
Phone: +91 99887 76655
""", [], False, 55),

    ("12_sales_missing_org", "Sam", "sam.k1987@gmail.com",
     "pricing",
     """hi, what is the price to automate our reports? we want a quote.
""", [], False, 60),

    ("13_support_with_order", "Farah Ali", "farah@greenleaf-foods.in",
     "Report automation stopped - ORD-20417",
     """Hello Support,

Since your update last Friday, the daily sales report workflow you built for us has stopped sending emails. There is no error message, it just does not run. Order reference ORD-20417.

This is urgent as our managers rely on it every morning.

Thanks,
Farah Ali
Greenleaf Foods Pvt Ltd
Phone: +91 98200 33445
""", [], False, 66),

    ("14_support_no_order", "Tom Mathew", "tom.mathew@brightpath.in",
     "Bot not working",
     """Hi,

The lead capture bot on our website is not working since yesterday. Form entries are not reaching our CRM. Please fix asap.

Tom
""", [], False, 70),

    ("15_support_ticket", "Lina George", "lina.george@harbourhealth.in",
     "TKT-5581 - sync error",
     """Hello,

We are seeing an error in the patient sync integration: records created after 6pm are missing the next day. Ticket TKT-5581 was raised last week but we have no update. Can someone help?

Regards,
Lina George
Harbour Health Hospital
Phone: +91 98450 99887
""", [], False, 75),

    ("16_vendor_seo", "Digital Growth Team", "growth@rankfast-seo.com",
     "Rank on Google page 1 in 30 days",
     """Hello,

We provide SEO and lead generation services for IT companies. Our agency can get your website to rank on Google page 1 with quality backlinks. Special discount this month only.

Reply for our rate card.

Team RankFast
""", [], False, 80),

    ("17_vendor_outsourcing", "Ravi Kumar", "ravi@codecraft-outsourcing.com",
     "Outsourcing partner for your development work",
     """Dear Sir,

We are a 40-person development agency and we offer outsourcing services for automation and integration projects. We can work as a white-label partner at an hourly rate of $18 per hour.

Our services include Python, n8n and API integrations. Can we set up a call?

Regards,
Ravi Kumar
CodeCraft Outsourcing
""", [], False, 85),

    ("18_spam_lottery", "Prize Department", "claims@global-prize-win.biz",
     "CONGRATULATIONS!!! You are a WINNER",
     """Congratulations! Your email has won the international lottery jackpot of $1,500,000.

Click here to claim your prize now: http://claim-prize.example/now
Act now, limited time offer!
""", [], False, 90),

    ("19_spam_crypto", "Investment Desk", "desk@crypto-returns.example",
     "Guaranteed returns 40% monthly",
     """Exclusive investment opportunity in bitcoin with guaranteed returns of 40% every month.

http://a.example http://b.example http://c.example http://d.example
Click the link to join.
""", [], False, 95),

    ("20_spam_phishing", "Mail Admin", "security@mail-verify.example",
     "Action required: verify your account",
     """Dear user,

Your mailbox will be suspended. Verify your account password within 24 hours by clicking the link below.

http://verify-mailbox.example/login
""", [], False, 100),

    ("21_unknown_vague", "Deepak", "deepak.v@gmail.com",
     "Hi",
     """Are you free this week? Let me know.
""", [], False, 105),

    ("22_empty_body", "Unknown Sender", "noreply@forms.example",
     "New form submission",
     "", [], False, 110),

    ("23_ambiguous_student_quote", "Ishita Bose", "ishita.bose@greenfield.ac.in",
     "Workshop for our students - pricing?",
     """Hello,

I am a student coordinator at Greenfield Institute of Technology. Our club would like to host a workshop on automation for our students. Could you share pricing for a 2-hour session? We are also interested in any internship opportunities for our members.

Regards,
Ishita Bose
""", [], False, 115),

    ("24_support_forwarded_thread", "Anil Desai", "anil.desai@greenleaf-foods.in",
     "Fwd: Report automation stopped - ORD-20417",
     """Adding my colleague's note below. Same issue on our side - the workflow failed again today.

Anil Desai
Greenleaf Foods Pvt Ltd

---------- Forwarded message ---------
From: Farah Ali
Subject: Report automation stopped - ORD-20417

Since your update last Friday, the daily sales report workflow you built for us has stopped sending emails.
""", [], False, 120),

    ("25_sales_detailed", "Harsh Vardhan", "harsh@vardhan-traders.in",
     "Proposal request: order-to-cash automation",
     """Dear Team,

We are a wholesale distributor with 12 staff. Today an order comes in by WhatsApp, someone types it into Excel, then into Tally, then an invoice is emailed by hand. Payments are chased by phone.

We want to automate our order-to-cash process end to end. Could you send a proposal with a cost estimate? Our budget is ₹6 lakh and we would like phase one live by March.

I am happy to schedule a call next week.

Warm regards,
Harsh Vardhan
Director, Vardhan Traders
Phone: +91 93222 44556
""", [], False, 126),

    ("26_internship_mixed_language", "Pooja Yadav", "pooja.yadav@nsis.ac.in",
     "Internship ke liye request",
     """Namaste,

Main National School of Inference Sciences mein M.Sc ki student hoon, aur main ek internship dhoond rahi hoon. Mujhe Python aur Excel aata hai. I expect to graduate in 2027. CV attach kar diya hai.

Dhanyavaad,
Pooja Yadav
Phone: +91 94444 55566
""", ["Pooja_Yadav_CV.pdf"], False, 130),

    ("27_vendor_partnership", "Elena Park", "elena@cloudbridge.example",
     "Partnership: white-label AI chatbots",
     """Hi,

We provide a white-label AI chatbot platform and are looking for reseller partners in India. Partnership terms include a 30% margin. Would you be open to collaboration?

Best,
Elena Park
CloudBridge
""", [], False, 136),

    ("28_sales_subject_only", "Gaurav Sethi", "gaurav@sethi-motors.in",
     "Quote for automating our service booking",
     """Please call me.

Gaurav Sethi
Sethi Motors
+91 98989 89898
""", [], False, 140),

    ("29_support_refund", "Kavya Reddy", "kavya@brightpath.in",
     "Cancel and refund - INV-7730",
     """Hello,

The integration we bought is still failing after two fixes. We would like to cancel the remaining work and discuss a refund for invoice INV-7730.

Regards,
Kavya Reddy
BrightPath Learning
Phone: +91 97000 12121
""", [], False, 146),

    ("30_internship_class_of", "Daniel Thomas", "daniel.thomas@lakeview.edu",
     "Internship - process automation",
     """Hi Team,

I am an undergraduate at Lakeview University (class of 2027) studying economics and data science. I am interested in an internship in process automation. I have used Python, SQL, Excel and Make.com, and can give 20 hours per week. Resume attached.

Thanks and regards,
Daniel Thomas
Lakeview University
Mobile: +91 95555 66677
LinkedIn: https://www.linkedin.com/in/daniel-thomas-demo
""", ["Daniel_Thomas_Resume.pdf"], False, 150),
]


def build(stem, name, addr, subject, body, attachments, html_only, hours, bodies) -> EmailMessage:
    if body is None:  # duplicate: reuse the original body exactly
        body = bodies["01_internship_complete"]
    bodies[stem] = body

    msg = EmailMessage()
    msg["From"] = f"{name} <{addr}>"
    msg["To"] = "hello@example-automation.co"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(BASE + timedelta(hours=hours))
    msg["Message-ID"] = make_msgid(idstring=stem, domain="sample.local")
    if html_only:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    for filename in attachments:
        msg.add_attachment(b"%PDF-1.4 sample file\n", maintype="application",
                           subtype="pdf", filename=filename)
    return msg


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.eml"):
        old.unlink()
    bodies: dict[str, str] = {}
    for row in EMAILS:
        msg = build(*row, bodies=bodies)
        (OUT / f"{row[0]}.eml").write_bytes(bytes(msg))
    print(f"Wrote {len(EMAILS)} emails to {OUT}")


if __name__ == "__main__":
    main()
