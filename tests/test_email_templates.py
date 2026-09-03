import pytest

from app.services import email_templates
from app.services.email_service import (
    _build_password_reset_success_email,
    _build_registration_success_email,
)


def test_render_email_shell_includes_logo_and_preheader():
    html_out = email_templates.render_email_shell(
        preheader="hello preheader",
        body_html="<tr><td>inner</td></tr>",
    )
    assert "hello preheader" in html_out
    assert "<tr><td>inner</td></tr>" in html_out
    assert "prefers-color-scheme: dark" in html_out
    # Logo must be a real hosted URL — Gmail/Outlook strip base64 data-URI
    # images in HTML email, so embedding is not viable.
    assert "res.cloudinary.com" in html_out
    assert "axiora_pulse_logo.png" in html_out
    assert "axiora_logo.png" in html_out
    assert "data:image/png;base64," not in html_out
    assert 'class="logo-light"' in html_out
    assert 'class="logo-dark"' in html_out


def test_render_email_shell_logo_url_is_configurable(monkeypatch):
    monkeypatch.setattr(email_templates, "_LOGO_LIGHT_URL", "https://cdn.example.com/light.png")
    monkeypatch.setattr(email_templates, "_LOGO_DARK_URL", "https://cdn.example.com/dark.png")
    html_out = email_templates.render_email_shell(preheader="x", body_html="<tr><td>y</td></tr>")
    assert "https://cdn.example.com/light.png" in html_out
    assert "https://cdn.example.com/dark.png" in html_out


def test_render_email_shell_escapes_preheader():
    html_out = email_templates.render_email_shell(
        preheader='<script>alert(1)</script>',
        body_html="<tr><td>x</td></tr>",
    )
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_render_button_escapes_url_and_label():
    html_out = email_templates.render_button('Click "me"', "https://example.com/?a=1&b=2")
    assert 'href="https://example.com/?a=1&amp;b=2"' in html_out
    assert "Click &quot;me&quot;" in html_out


def test_build_registration_success_email_contains_welcome_content():
    msg = _build_registration_success_email("newuser@axiorapulse.com", display_name="Newbie")
    assert msg["Subject"] == "Welcome to Axiora Pulse — Your Account is Ready"
    assert msg["To"] == "newuser@axiorapulse.com"

    parts = {part.get_content_type(): part.get_payload(decode=True).decode("utf-8") for part in msg.walk() if part.get_content_type() in ("text/plain", "text/html")}
    assert "Newbie" in parts["text/plain"]
    assert "Welcome to Axiora Pulse" in parts["text/html"]
    assert "Go to Dashboard" in parts["text/html"]
    # The CTA must point at the real frontend login page, not the backend API URL.
    assert "https://qa.axiorapulse.com/login" in parts["text/html"]
    assert "https://qa.axiorapulse.com/login" in parts["text/plain"]


def test_build_password_reset_success_email_excludes_password():
    msg = _build_password_reset_success_email("user@axiorapulse.com")
    assert msg["Subject"] == "Your Axiora Pulse Password Was Changed"

    parts = {part.get_content_type(): part.get_payload(decode=True).decode("utf-8") for part in msg.walk() if part.get_content_type() in ("text/plain", "text/html")}
    combined = parts["text/plain"] + parts["text/html"]
    assert "password" in combined.lower()
    # Must never leak the actual credential value.
    assert "Test@12345" not in combined
    assert "Didn" in parts["text/html"]  # security warning present


def test_build_registration_success_email_escapes_html_in_display_name():
    msg = _build_registration_success_email("x@axiorapulse.com", display_name="<b>hax</b>")
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    html_body = html_part.get_payload(decode=True).decode("utf-8")
    assert "<b>hax</b>" not in html_body
    assert "&lt;b&gt;hax&lt;/b&gt;" in html_body


def test_build_survey_response_notification_email():
    from app.services.email_service import _build_survey_response_notification_email

    questions = [
        {"id": 1, "question": "What is your main challenge?", "questionType": "text"},
        {"id": 2, "question": "Budget range?", "questionType": "radio"},
    ]
    answers = [
        {"questionId": 1, "answer": "Managing client feedback"},
        {"questionId": 2, "answer": "$50/mo"},
    ]

    msg = _build_survey_response_notification_email(
        to_email="owner@axiorapulse.com",
        workspace_name="Acme Workspace",
        workspace_id=42,
        survey_id=7,
        respondent_email="respondent@example.com",
        questions=questions,
        answers=answers,
    )

    assert "New Survey Response Received" in msg["Subject"]
    assert "Acme Workspace" in msg["Subject"]
    assert msg["To"] == "owner@axiorapulse.com"

    parts = {
        part.get_content_type(): part.get_payload(decode=True).decode("utf-8")
        for part in msg.walk()
        if part.get_content_type() in ("text/plain", "text/html")
    }

    assert "Acme Workspace" in parts["text/html"]
    assert "respondent@example.com" in parts["text/html"]
    assert "What is your main challenge?" in parts["text/html"]
    assert "Managing client feedback" in parts["text/html"]
    assert "View Survey &amp; Run Analysis" in parts["text/html"] or "View Survey & Run Analysis" in parts["text/html"]
    assert "What is your main challenge?" in parts["text/plain"]
    assert "Managing client feedback" in parts["text/plain"]

