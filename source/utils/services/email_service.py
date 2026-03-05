"""
Email Service — facade for sending emails via background tasks

Uses FastAPI BackgroundTasks to send emails without blocking the request.
Templates are rendered by Jinja2 in utils/tasks/email_tasks.py.
"""

import secrets
import logging
from fastapi import BackgroundTasks

from utils.tasks.email_tasks import (
    send_invitation_email,
    send_password_reset_email,
    send_welcome_email,
    send_contract_expiry_warning_email,
    send_contract_expired_email,
)

logger = logging.getLogger(__name__)


class EmailService:
    """Email service facade — schedules emails as background tasks."""

    @staticmethod
    def generate_temporary_password(length: int = 12) -> str:
        """Generate a secure temporary password."""
        return secrets.token_urlsafe(length)[:length]

    @staticmethod
    def send_operator_invitation(
        background_tasks: BackgroundTasks,
        to_email: str,
        company_name: str,
        temporary_password: str,
        invited_by: str,
        role_display: str = "an operator",
        login_url: str = "https://yourcompany.crm.com",
    ) -> None:
        """Schedule operator invitation email as a background task."""
        background_tasks.add_task(
            send_invitation_email,
            to_email=to_email,
            company_name=company_name,
            temporary_password=temporary_password,
            invited_by=invited_by,
            role_display=role_display,
            login_url=login_url,
        )

    @staticmethod
    def send_admin_invitation(
        background_tasks: BackgroundTasks,
        to_email: str,
        company_name: str,
        temporary_password: str,
        invited_by: str,
        login_url: str = "https://yourcompany.crm.com",
    ) -> None:
        """Schedule admin invitation email as a background task."""
        background_tasks.add_task(
            send_invitation_email,
            to_email=to_email,
            company_name=company_name,
            temporary_password=temporary_password,
            invited_by=invited_by,
            role_display="a Company Administrator",
            login_url=login_url,
        )

    @staticmethod
    def send_password_reset(
        background_tasks: BackgroundTasks,
        to_email: str,
        reset_token: str,
        reset_url: str = "https://yourcompany.crm.com/reset-password",
        company_name: str = "S1P CRM",
    ) -> None:
        """Schedule password reset email as a background task."""
        background_tasks.add_task(
            send_password_reset_email,
            to_email=to_email,
            reset_token=reset_token,
            reset_url=reset_url,
            company_name=company_name,
        )

    @staticmethod
    def send_welcome(
        background_tasks: BackgroundTasks,
        to_email: str,
        user_name: str,
        company_name: str,
        login_url: str = "https://yourcompany.crm.com",
    ) -> None:
        """Schedule welcome email as a background task."""
        background_tasks.add_task(
            send_welcome_email,
            to_email=to_email,
            user_name=user_name,
            company_name=company_name,
            login_url=login_url,
        )

    @staticmethod
    def send_contract_expiry_warning(
        background_tasks: BackgroundTasks,
        to_email: str,
        company_name: str,
        contract_name: str,
        days_remaining: int,
        end_date: str,
        grace_period_days: int,
        renew_url: str,
    ) -> None:
        """Schedule contract expiry warning email as a background task."""
        background_tasks.add_task(
            send_contract_expiry_warning_email,
            to_email=to_email,
            company_name=company_name,
            contract_name=contract_name,
            days_remaining=days_remaining,
            end_date=end_date,
            grace_period_days=grace_period_days,
            renew_url=renew_url,
        )

    @staticmethod
    def send_contract_expired(
        background_tasks: BackgroundTasks,
        to_email: str,
        company_name: str,
        contract_name: str,
        end_date: str,
        in_grace_period: bool,
        grace_days_remaining: int,
        renew_url: str,
    ) -> None:
        """Schedule contract expired email as a background task."""
        background_tasks.add_task(
            send_contract_expired_email,
            to_email=to_email,
            company_name=company_name,
            contract_name=contract_name,
            end_date=end_date,
            in_grace_period=in_grace_period,
            grace_days_remaining=grace_days_remaining,
            renew_url=renew_url,
        )
