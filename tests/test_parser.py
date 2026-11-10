from triage.parser import fingerprint, html_to_text


def test_plain_email_fields(email_factory):
    e = email_factory("Hello there, this is the body.", subject="Hi", sender="Asha K <Asha@Example.com>",
                      attachments=("cv.pdf",))
    assert e.sender_name == "Asha K"
    assert e.sender_email == "asha@example.com"  # normalised to lower case
    assert e.subject == "Hi"
    assert e.body == "Hello there, this is the body."
    assert e.attachments == ["cv.pdf"]
    assert e.received_at is not None and e.received_at.year == 2026


def test_html_only_email_is_converted_to_text(email_factory):
    e = email_factory("<p>Hello <b>team</b></p><p>Second&nbsp;line</p>", html=True)
    assert "<" not in e.body
    assert "Hello team" in e.body
    assert "Second" in e.body


def test_missing_subject_gets_placeholder(email_factory):
    assert email_factory("body text", subject="").subject == "(no subject)"


def test_fingerprint_ignores_whitespace_and_case():
    a = fingerprint("x@y.com", "Hello", "Line one\n\nline   two")
    b = fingerprint("X@Y.com", "hello", "line one line two")
    assert a == b


def test_fingerprint_changes_with_content():
    assert fingerprint("x@y.com", "Hello", "one") != fingerprint("x@y.com", "Hello", "two")


def test_html_to_text_unescapes_entities():
    assert html_to_text("Tom &amp; Jerry<br>next") == "Tom & Jerry\nnext"
