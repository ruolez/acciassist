"""Transactional email bodies. Each function returns (subject, html, text)."""

from html import escape

_NAVY = "#182a63"
_GOLD = "#f5c44c"
_INK = "#1d2333"
_MUTED = "#5b6478"


def _button(url: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">'
        f'<tr><td style="border-radius:8px;background:{_GOLD};">'
        f'<a href="{escape(url, quote=True)}" '
        f'style="display:inline-block;padding:13px 28px;font-weight:700;'
        f'color:{_NAVY};text-decoration:none;font-size:16px;">{escape(label)}</a>'
        f"</td></tr></table>"
    )


def _layout(heading: str, body_html: str) -> str:
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f8;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
<tr><td style="background:{_NAVY};padding:20px 32px;">
<span style="color:#ffffff;font-size:20px;font-weight:800;letter-spacing:0.5px;">AcciAssist</span>
</td></tr>
<tr><td style="padding:32px;">
<h1 style="margin:0 0 16px;font-size:22px;color:{_INK};">{escape(heading)}</h1>
{body_html}
</td></tr>
<tr><td style="padding:20px 32px;border-top:1px solid #e6e8ee;">
<p style="margin:0;font-size:12px;color:{_MUTED};">You are receiving this email because your contact details were submitted on AcciAssist. If this wasn't you, you can ignore this message.</p>
</td></tr>
</table>
</td></tr></table>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{_INK};">{text}</p>'


def _estimate_html(estimate: str | None) -> str:
    if not estimate:
        return ""
    return (
        f'<div style="margin:18px 0;padding:16px 20px;background:{_NAVY};border-radius:10px;">'
        f'<span style="display:block;font-size:12px;color:#c8d0e8;text-transform:uppercase;'
        f'letter-spacing:1px;">Estimated settlement range</span>'
        f'<span style="display:block;margin-top:6px;font-size:22px;font-weight:800;'
        f'color:{_GOLD};">{escape(estimate)}</span></div>'
    )


def lead_received_claim(
    name: str, estimate: str | None, claim_url: str
) -> tuple[str, str, str]:
    subject = "We received your case — create your AcciAssist account"
    body = (
        _paragraph(f"Hi {escape(name)},")
        + _paragraph(
            "Thank you for telling us about your accident. Our specialists are "
            "reviewing your answers and will reach out shortly."
        )
        + _estimate_html(estimate)
        + _paragraph(
            "Create your account to follow your case's progress, see updates from "
            "our team, and review your intake summary any time."
        )
        + _button(claim_url, "Create your account")
        + _paragraph(
            '<span style="font-size:13px;color:' + _MUTED + ';">This link is personal '
            "to you and expires in 7 days.</span>"
        )
    )
    text = (
        f"Hi {name},\n\n"
        "Thank you for telling us about your accident. Our specialists are reviewing "
        "your answers and will reach out shortly.\n\n"
        + (f"Estimated settlement range: {estimate}\n\n" if estimate else "")
        + "Create your account to follow your case's progress:\n"
        f"{claim_url}\n\n"
        "This link is personal to you and expires in 7 days.\n"
    )
    return subject, _layout("We received your case", body), text


def lead_received_existing(
    name: str, estimate: str | None, login_url: str
) -> tuple[str, str, str]:
    subject = "We received your new case — view it on AcciAssist"
    body = (
        _paragraph(f"Hi {escape(name)},")
        + _paragraph(
            "Thanks for submitting another case. It has been added to your "
            "AcciAssist account, and our specialists are reviewing it now."
        )
        + _estimate_html(estimate)
        + _button(login_url, "Log in to view your case")
    )
    text = (
        f"Hi {name},\n\n"
        "Thanks for submitting another case. It has been added to your AcciAssist "
        "account, and our specialists are reviewing it now.\n\n"
        + (f"Estimated settlement range: {estimate}\n\n" if estimate else "")
        + f"Log in to view your case: {login_url}\n"
    )
    return subject, _layout("We received your new case", body), text


def password_reset(name: str, reset_url: str) -> tuple[str, str, str]:
    subject = "Reset your AcciAssist password"
    body = (
        _paragraph(f"Hi {escape(name)},")
        + _paragraph(
            "We received a request to reset your password. Click the button below "
            "to choose a new one."
        )
        + _button(reset_url, "Reset password")
        + _paragraph(
            '<span style="font-size:13px;color:' + _MUTED + ';">This link expires in '
            "1 hour. If you didn't request a reset, you can ignore this email.</span>"
        )
    )
    text = (
        f"Hi {name},\n\n"
        "We received a request to reset your password. Open this link to choose a "
        f"new one:\n{reset_url}\n\n"
        "This link expires in 1 hour. If you didn't request a reset, you can ignore "
        "this email.\n"
    )
    return subject, _layout("Reset your password", body), text


def stage_changed(name: str, stage_label: str, dashboard_url: str) -> tuple[str, str, str]:
    subject = f"Your case moved to: {stage_label}"
    body = (
        _paragraph(f"Hi {escape(name)},")
        + _paragraph(
            f"Your case status was updated to <strong>{escape(stage_label)}</strong>."
        )
        + _button(dashboard_url, "View your case")
    )
    text = (
        f"Hi {name},\n\n"
        f"Your case status was updated to: {stage_label}.\n\n"
        f"View your case: {dashboard_url}\n"
    )
    return subject, _layout("Your case status changed", body), text


def case_update_posted(name: str, dashboard_url: str) -> tuple[str, str, str]:
    subject = "New update on your AcciAssist case"
    body = (
        _paragraph(f"Hi {escape(name)},")
        + _paragraph("Our team posted a new update on your case. Log in to read it.")
        + _button(dashboard_url, "Read the update")
    )
    text = (
        f"Hi {name},\n\n"
        "Our team posted a new update on your case. Log in to read it:\n"
        f"{dashboard_url}\n"
    )
    return subject, _layout("New update on your case", body), text


def test_email() -> tuple[str, str, str]:
    subject = "AcciAssist SMTP test"
    body = _paragraph(
        "This is a test email from your AcciAssist admin settings. "
        "If you can read this, SMTP is configured correctly."
    )
    text = (
        "This is a test email from your AcciAssist admin settings. "
        "If you can read this, SMTP is configured correctly.\n"
    )
    return subject, _layout("SMTP test successful", body), text
