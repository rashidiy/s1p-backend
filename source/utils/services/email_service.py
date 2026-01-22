"""
Email Service for sending invitations and notifications

For production: Replace with actual SMTP (SendGrid, AWS SES, etc.)
For now: Logs email content (can be sent via background job)
"""

import logging
import secrets
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for user invitations and notifications"""

    @staticmethod
    def generate_temporary_password(length: int = 12) -> str:
        """
        Generate a secure temporary password

        Args:
            length: Password length (default: 12)

        Returns:
            Random password string
        """
        # Use URL-safe characters for easy copy-paste
        return secrets.token_urlsafe(length)[:length]

    @staticmethod
    async def send_operator_invitation(
        to_email: str,
        company_name: str,
        temporary_password: str,
        invited_by: str,
        login_url: str = "https://yourcompany.crm.com"
    ) -> bool:
        """
        Send operator invitation email

        Args:
            to_email: Recipient email
            company_name: Company name
            temporary_password: Temporary password for first login
            invited_by: Name of person who sent invitation
            login_url: Login URL (should be company subdomain)

        Returns:
            True if email sent successfully
        """
        subject = f"You've been invited to {company_name} CRM"

        body = f"""
Hello,

{invited_by} has invited you to join {company_name}'s CRM system as an operator.

Your login credentials:
Email: {to_email}
Temporary Password: {temporary_password}

Login URL: {login_url}

IMPORTANT: You must change your password after first login.

Your temporary password will expire in 7 days.

If you have any questions, please contact your administrator.

Best regards,
{company_name} Team
        """.strip()

        # For production: Send actual email via SMTP/SendGrid/SES
        # For now: Log the email
        logger.info(f"""
========================================
EMAIL SENT TO: {to_email}
SUBJECT: {subject}
BODY:
{body}
========================================
        """)

        # TODO: Integrate with actual email service
        # Example:
        # await smtp_client.send_email(to_email, subject, body)

        return True

    @staticmethod
    async def send_password_reset(
        to_email: str,
        reset_token: str,
        reset_url: str = "https://yourcompany.crm.com/reset-password"
    ) -> bool:
        """
        Send password reset email

        Args:
            to_email: Recipient email
            reset_token: Password reset token
            reset_url: Password reset URL

        Returns:
            True if email sent successfully
        """
        subject = "Password Reset Request"

        body = f"""
Hello,

We received a request to reset your password.

Click the link below to reset your password:
{reset_url}?token={reset_token}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.

Best regards,
CRM Team
        """.strip()

        logger.info(f"""
========================================
PASSWORD RESET EMAIL TO: {to_email}
SUBJECT: {subject}
BODY:
{body}
========================================
        """)

        # TODO: Integrate with actual email service
        return True

    @staticmethod
    async def send_welcome_email(
        to_email: str,
        user_name: str,
        company_name: str
    ) -> bool:
        """
        Send welcome email after operator completes registration

        Args:
            to_email: Recipient email
            user_name: User's full name
            company_name: Company name

        Returns:
            True if email sent successfully
        """
        subject = f"Welcome to {company_name} CRM!"

        body = f"""
Hi {user_name},

Welcome to {company_name}'s CRM system!

You're all set up and ready to go. Here's what you can do:

✓ Make and receive calls
✓ Manage your leads and contacts
✓ Track your deals
✓ Complete tasks
✓ View your performance analytics

If you need any help, don't hesitate to reach out to your administrator.

Best regards,
{company_name} Team
        """.strip()

        logger.info(f"""
========================================
WELCOME EMAIL TO: {to_email}
SUBJECT: {subject}
BODY:
{body}
========================================
        """)

        return True
