"""
Background email tasks

Uses FastAPI BackgroundTasks for async email sending.
Can be migrated to ARQ/Celery for queue-based processing in the future.
"""

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import SMTPConfig

logger = logging.getLogger(__name__)

# Template engine — loaded once, reused across tasks
_template_env = Environment(
    loader=FileSystemLoader("source/templates/email"),
    autoescape=select_autoescape(["html"]),
)


def render_template(template_name: str, **context) -> str:
    """Render a Jinja2 email template to HTML string."""
    from datetime import datetime
    context.setdefault("year", datetime.now().year)
    template = _template_env.get_template(template_name)
    return template.render(**context)


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an email via SMTP.

    When SMTP is disabled (SMTP_ENABLED=false), logs the email instead of sending.
    This is the core send function — all other email tasks call this.
    """
    if not SMTPConfig.ENABLED:
        logger.info(f"[EMAIL-DEV] To: {to_email} | Subject: {subject}")
        logger.debug(f"[EMAIL-DEV] Body preview: {html_body[:200]}...")
        return True

    try:
        message = MIMEMultipart("alternative")
        message["From"] = f"{SMTPConfig.FROM_NAME} <{SMTPConfig.FROM_EMAIL}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            message,
            hostname=SMTPConfig.HOST,
            port=SMTPConfig.PORT,
            username=SMTPConfig.USER,
            password=SMTPConfig.PASSWORD,
            start_tls=SMTPConfig.USE_TLS,
        )

        logger.info(f"Email sent to {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


async def send_invitation_email(
    to_email: str,
    company_name: str,
    temporary_password: str,
    invited_by: str,
    role_display: str,
    login_url: str,
) -> bool:
    """Send operator/admin invitation email."""
    html = render_template(
        "invitation.html",
        to_email=to_email,
        company_name=company_name,
        temporary_password=temporary_password,
        invited_by=invited_by,
        role_display=role_display,
        login_url=login_url,
    )
    return await send_email(
        to_email=to_email,
        subject=f"You've been invited to {company_name}",
        html_body=html,
    )


async def send_admin_invitation_email(
    to_email: str,
    first_name: str,
    company_name: str,
    set_password_url: str,
) -> bool:
    """Send admin invitation email with set-password link."""
    html = render_template(
        "admin_invitation.html",
        first_name=first_name,
        company_name=company_name,
        set_password_url=set_password_url,
    )
    return await send_email(
        to_email=to_email,
        subject=f"You've been invited to S1P - {company_name}",
        html_body=html,
    )


async def send_password_reset_email(
    to_email: str,
    reset_token: str,
    reset_url: str,
    company_name: str = "S1P CRM",
) -> bool:
    """Send password reset email."""
    html = render_template(
        "password_reset.html",
        to_email=to_email,
        reset_token=reset_token,
        reset_url=reset_url,
        company_name=company_name,
    )
    return await send_email(
        to_email=to_email,
        subject="Password Reset Request",
        html_body=html,
    )


async def send_welcome_email(
    to_email: str,
    user_name: str,
    company_name: str,
    login_url: str,
) -> bool:
    """Send welcome email after password change."""
    html = render_template(
        "welcome.html",
        user_name=user_name,
        company_name=company_name,
        login_url=login_url,
    )
    return await send_email(
        to_email=to_email,
        subject=f"Welcome to {company_name}!",
        html_body=html,
    )


async def send_contract_expiry_warning_email(
    to_email: str,
    company_name: str,
    contract_name: str,
    days_remaining: int,
    end_date: str,
    grace_period_days: int,
    renew_url: str,
) -> bool:
    """Send contract expiry warning to owner."""
    html = render_template(
        "contract_expiry_warning.html",
        company_name=company_name,
        contract_name=contract_name,
        days_remaining=days_remaining,
        end_date=end_date,
        grace_period_days=grace_period_days,
        renew_url=renew_url,
    )
    return await send_email(
        to_email=to_email,
        subject=f"Contract expiring soon: {company_name}",
        html_body=html,
    )


async def send_contract_expired_email(
    to_email: str,
    company_name: str,
    contract_name: str,
    end_date: str,
    in_grace_period: bool,
    grace_days_remaining: int,
    renew_url: str,
) -> bool:
    """Send contract expired notification to owner."""
    html = render_template(
        "contract_expired.html",
        company_name=company_name,
        contract_name=contract_name,
        end_date=end_date,
        in_grace_period=in_grace_period,
        grace_days_remaining=grace_days_remaining,
        renew_url=renew_url,
    )
    return await send_email(
        to_email=to_email,
        subject=f"Contract expired: {company_name}",
        html_body=html,
    )
