"""
Email Service - Resend Integration.

Provides transactional email functionality:
- Password reset emails
- Welcome emails
- Notification emails
"""

import os
import asyncio
import logging
import resend
from typing import Optional, Dict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_app_url():
    """Get APP_URL - reads directly from .env file to avoid supervisor override."""
    from pathlib import Path
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.startswith('APP_URL='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    # Fallback to environment variable then default
    return os.environ.get('APP_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com')


def get_sender_email():
    """Get SENDER_EMAIL from environment."""
    return os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')


def get_sender_name():
    """Get SENDER_NAME from environment."""
    return os.environ.get('SENDER_NAME', 'NeoNoble Ramp')


class EmailService:
    """
    Email service using Resend API.
    
    Features:
    - Async non-blocking email sending
    - HTML email templates
    - Password reset flow
    """
    
    def __init__(self):
        self._initialized = False
        self._api_key = None
        
    async def initialize(self):
        """Initialize email service."""
        if self._initialized:
            return
        
        self._api_key = os.environ.get('RESEND_API_KEY', '')
        
        if self._api_key:
            resend.api_key = self._api_key
            logger.info(f"Email Service initialized with Resend (sender: {get_sender_email()})")
        else:
            logger.warning("Email Service initialized WITHOUT API KEY - emails will not be sent")
        
        self._initialized = True
    
    def is_configured(self) -> bool:
        """Check if email service is configured."""
        return bool(self._api_key)
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Dict:
        """
        Send an email using Resend.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (improves deliverability)
            from_email: Optional sender email (defaults to SENDER_EMAIL)
            
        Returns:
            Dict with status and email_id
        """
        if not self._api_key:
            logger.warning(f"[EMAIL] Skipped (no API key): {subject} → {to_email}")
            return {"status": "skipped", "reason": "No API key configured"}
        
        sender_email = get_sender_email()
        sender_name = get_sender_name()
        sender = from_email or f"{sender_name} <{sender_email}>"
        
        params = {
            "from": sender,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "reply_to": sender_email
        }
        
        # Add plain text version for better deliverability
        if text_content:
            params["text"] = text_content
        
        try:
            # Run sync SDK in thread to keep FastAPI non-blocking
            email = await asyncio.to_thread(resend.Emails.send, params)
            
            logger.info(f"[EMAIL] Sent: {subject} → {to_email} (ID: {email.get('id')})")
            
            return {
                "status": "success",
                "email_id": email.get("id"),
                "to": to_email
            }
        except Exception as e:
            logger.error(f"[EMAIL] Failed: {subject} → {to_email} | Error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "to": to_email
            }
    
    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        user_name: Optional[str] = None
    ) -> Dict:
        """
        Send password reset email.
        
        Args:
            to_email: User's email address
            reset_token: Password reset token
            user_name: Optional user name for personalization
        """
        app_url = get_app_url()
        reset_link = f"{app_url}/reset-password?token={reset_token}"
        
        # Plain text version for better deliverability
        greeting = f"Ciao {user_name}," if user_name else "Ciao,"
        text_content = f"""{greeting}

Abbiamo ricevuto una richiesta per reimpostare la password del tuo account NeoNoble Ramp.

Per creare una nuova password, visita questo link:
{reset_link}

Se non hai richiesto il reset della password, puoi ignorare questa email.
Il link scadrà tra 1 ora.

---
NeoNoble Ramp
https://neonobleramp.com
"""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <!-- Header -->
                <tr>
                    <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">
                            Reimposta Password
                        </h1>
                        <p style="color: #e0e0e0; margin: 10px 0 0 0; font-size: 14px;">NeoNoble Ramp</p>
                    </td>
                </tr>
                
                <!-- Content -->
                <tr>
                    <td style="padding: 40px 30px;">
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            {greeting}
                        </p>
                        
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            Abbiamo ricevuto una richiesta per reimpostare la password del tuo account NeoNoble Ramp.
                        </p>
                        
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                            Clicca il pulsante qui sotto per creare una nuova password:
                        </p>
                        
                        <!-- Button -->
                        <table width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td align="center">
                                    <a href="{reset_link}" 
                                       style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                              color: #ffffff; text-decoration: none; padding: 15px 40px; 
                                              border-radius: 8px; font-size: 16px; font-weight: 600;">
                                        Reimposta Password
                                    </a>
                                </td>
                            </tr>
                        </table>
                        
                        <p style="color: #666666; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                            Se non hai richiesto il reset della password, puoi ignorare questa email. 
                            Il link scadrà tra <strong>1 ora</strong>.
                        </p>
                        
                        <p style="color: #999999; font-size: 12px; line-height: 1.6; margin: 20px 0 0 0;">
                            Se il pulsante non funziona, copia e incolla questo link nel browser:<br>
                            <a href="{reset_link}" style="color: #667eea; word-break: break-all;">{reset_link}</a>
                        </p>
                    </td>
                </tr>
                
                <!-- Footer -->
                <tr>
                    <td style="background-color: #f8f9fa; padding: 20px 30px; text-align: center; border-top: 1px solid #e9ecef;">
                        <p style="color: #999999; font-size: 12px; margin: 0;">
                            © 2026 NeoNoble Ramp. Tutti i diritti riservati.<br>
                            <a href="https://neonobleramp.com" style="color: #667eea;">neonobleramp.com</a>
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject="Reimposta la tua password - NeoNoble Ramp",
            html_content=html_content,
            text_content=text_content
        )
    
    async def send_password_changed_email(
        self,
        to_email: str,
        user_name: Optional[str] = None
    ) -> Dict:
        """
        Send password changed confirmation email.
        """
        greeting = f"Ciao {user_name}," if user_name else "Ciao,"
        current_time = datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')
        
        text_content = f"""{greeting}

La password del tuo account NeoNoble Ramp è stata aggiornata con successo.

Se non hai effettuato questa modifica, contattaci immediatamente.

Data: {current_time} UTC

---
NeoNoble Ramp
https://neonobleramp.com
"""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <!-- Header -->
                <tr>
                    <td style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 40px 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">
                            Password Aggiornata
                        </h1>
                        <p style="color: #e0e0e0; margin: 10px 0 0 0; font-size: 14px;">NeoNoble Ramp</p>
                    </td>
                </tr>
                
                <!-- Content -->
                <tr>
                    <td style="padding: 40px 30px;">
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            {greeting}
                        </p>
                        
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            La password del tuo account NeoNoble Ramp è stata aggiornata con successo.
                        </p>
                        
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            Se non hai effettuato questa modifica, contattaci immediatamente.
                        </p>
                        
                        <p style="color: #666666; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0;">
                            Data: {current_time} UTC
                        </p>
                    </td>
                </tr>
                
                <!-- Footer -->
                <tr>
                    <td style="background-color: #f8f9fa; padding: 20px 30px; text-align: center; border-top: 1px solid #e9ecef;">
                        <p style="color: #999999; font-size: 12px; margin: 0;">
                            © 2026 NeoNoble Ramp. Tutti i diritti riservati.<br>
                            <a href="https://neonobleramp.com" style="color: #667eea;">neonobleramp.com</a>
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject="Password aggiornata - NeoNoble Ramp",
            html_content=html_content,
            text_content=text_content
        )
    
    async def send_welcome_email(
        self,
        to_email: str,
        user_name: Optional[str] = None
    ) -> Dict:
        """
        Send welcome email to new users.
        """
        app_url = get_app_url()
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <!-- Header -->
                <tr>
                    <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                        <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">
                            Benvenuto su NeoNoble Ramp!
                        </h1>
                    </td>
                </tr>
                
                <!-- Content -->
                <tr>
                    <td style="padding: 40px 30px;">
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            {f'Ciao {user_name}!' if user_name else 'Ciao!'}
                        </p>
                        
                        <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            Il tuo account è stato creato con successo. Ora puoi accedere a tutte le funzionalità della piattaforma:
                        </p>
                        
                        <ul style="color: #333333; font-size: 16px; line-height: 1.8; padding-left: 20px;">
                            <li>Acquista crypto con carta o bonifico</li>
                            <li>Vendi crypto e ricevi EUR</li>
                            <li>Monitora le tue transazioni</li>
                        </ul>
                        
                        <!-- Button -->
                        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 30px;">
                            <tr>
                                <td align="center">
                                    <a href="{app_url}/dashboard" 
                                       style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                              color: #ffffff; text-decoration: none; padding: 15px 40px; 
                                              border-radius: 8px; font-size: 16px; font-weight: 600;">
                                        Vai alla Dashboard
                                    </a>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                
                <!-- Footer -->
                <tr>
                    <td style="background-color: #f8f9fa; padding: 20px 30px; text-align: center; border-top: 1px solid #e9ecef;">
                        <p style="color: #999999; font-size: 12px; margin: 0;">
                            © 2026 NeoNoble Ramp. Tutti i diritti riservati.
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return await self.send_email(
            to_email=to_email,
            subject="🎉 Benvenuto su NeoNoble Ramp!",
            html_content=html_content
        )


# Global instance
_email_service: Optional[EmailService] = None


def get_email_service() -> Optional[EmailService]:
    return _email_service


def set_email_service(service: EmailService):
    global _email_service
    _email_service = service
