import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

from sqlalchemy import select

from app.config import get_settings
from app.models.platform import NotificationIntegration
from app.services.notification.channels import integration_credentials
from app.services.tls import verified_tls_context


class AccountEmailError(RuntimeError):
    pass


def build_account_email(kind: str, display_name: str, username: str, code: str, expires_minutes: int | None = None) -> dict[str, str]:
    full_name = display_name.strip()
    invited = kind == "INVITE"
    subject = "Your NetMonitor account is ready" if invited else "Reset your NetMonitor password"
    heading = "Welcome to NetMonitor" if invited else "Password recovery"
    intro = (
        "An administrator created a secure NetMonitor account for you."
        if invited else "We received a request to reset the password for your NetMonitor account."
    )
    instruction = (
        "Sign in with the temporary password below. You will be required to choose a private password immediately."
        if invited else "Enter the verification code below on the recovery screen, then choose a new password."
    )
    expiry = "This temporary password is for first access only." if invited else f"This code expires in {expires_minutes} minutes and can be used once."
    plain = (
        f"{heading}\n\nHello {full_name},\n\n{intro}\n{instruction}\n\n"
        f"Username: {username}\n{'Temporary password' if invited else 'Verification code'}: {code}\n\n"
        f"{expiry}\n\nIf you did not expect this message, contact your NetMonitor administrator."
    )
    html = f"""<!doctype html><html><body style="margin:0;padding:28px;background:#eef2f7;font-family:Arial,sans-serif;color:#0f172a">
<div style="max-width:620px;margin:auto;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 12px 32px rgba(15,23,42,.12)">
  <div style="padding:24px 30px;background:#0f172a;color:#fff"><div style="font-size:12px;letter-spacing:.12em;color:#60a5fa;font-weight:700">NETMONITOR · SECURE ACCESS</div><h1 style="margin:9px 0 0;font-size:23px">{escape(heading)}</h1></div>
  <div style="padding:30px"><p style="font-size:16px;margin-top:0">Hello <strong>{escape(full_name)}</strong>,</p><p style="line-height:1.65;color:#475569">{escape(intro)} {escape(instruction)}</p>
  <div style="margin:24px 0;padding:18px;border:1px solid #dbeafe;border-radius:10px;background:#eff6ff"><div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Username</div><div style="margin:5px 0 18px;font-weight:700">{escape(username)}</div><div style="font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.08em">{'Temporary password' if invited else 'Verification code'}</div><div style="margin-top:8px;padding:12px;background:#fff;border:1px solid #bfdbfe;border-radius:7px;font-family:monospace;font-size:20px;font-weight:700;letter-spacing:.06em;word-break:break-all">{escape(code)}</div></div>
  <p style="font-size:13px;color:#64748b;line-height:1.55">{escape(expiry)} Never forward this message or share the credential.</p><p style="font-size:13px;color:#64748b">If you did not expect this message, contact your NetMonitor administrator.</p></div>
  <div style="padding:15px 30px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:11px">Automated security message · NetMonitor</div>
</div></body></html>"""
    return {"subject": subject, "plain": plain, "html": html}


async def send_account_email(db, recipient: str, content: dict[str, str]) -> None:
    item = (await db.execute(select(NotificationIntegration).where(
        NotificationIntegration.provider == "EMAIL", NotificationIntegration.enabled == True
    ))).scalar_one_or_none()
    if item is None:
        settings = get_settings()
        if not settings.SMTP_HOST or not settings.SMTP_FROM:
            raise AccountEmailError("Configure SMTP in Settings → Notifications, or provide SMTP_HOST and SMTP_FROM in the server environment.")
        config = {
            "smtp_server": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "username": settings.SMTP_USER,
            "from_address": settings.SMTP_FROM,
            "tls": settings.SMTP_PORT == 587,
            "ssl": settings.SMTP_PORT == 465,
        }
        secrets = {"password": settings.SMTP_PASSWORD}
    else:
        try:
            config, secrets = integration_credentials(item)
        except Exception as error:
            raise AccountEmailError("The SMTP Email credentials could not be read. Save the integration again.") from error
    if not config.get("smtp_server") or not config.get("from_address"):
        raise AccountEmailError("The SMTP Email integration is incomplete.")
    if config.get("username") and not secrets.get("password"):
        raise AccountEmailError("The SMTP Email password is not configured.")
    mail = EmailMessage()
    mail["Subject"], mail["From"], mail["To"] = content["subject"], config["from_address"], recipient
    mail.set_content(content["plain"])
    mail.add_alternative(content["html"], subtype="html")

    def deliver():
        smtp_class = smtplib.SMTP_SSL if config.get("ssl") else smtplib.SMTP
        kwargs = {"timeout": 10}
        if config.get("ssl"):
            kwargs["context"] = verified_tls_context()
        with smtp_class(config["smtp_server"], int(config.get("smtp_port", 587)), **kwargs) as smtp:
            if config.get("tls") and not config.get("ssl"):
                smtp.starttls(context=verified_tls_context())
            if config.get("username"):
                smtp.login(config["username"], secrets["password"])
            smtp.send_message(mail)

    try:
        await asyncio.to_thread(deliver)
    except smtplib.SMTPAuthenticationError as error:
        raise AccountEmailError("SMTP authentication was rejected. Verify the username and application password, then use Save & Test.") from error
    except smtplib.SMTPRecipientsRefused as error:
        raise AccountEmailError("The SMTP server rejected the new user's email address.") from error
    except ssl.SSLError as error:
        raise AccountEmailError("The SMTP TLS certificate or encryption mode was rejected. Verify STARTTLS/Implicit TLS settings.") from error
    except (TimeoutError, OSError) as error:
        raise AccountEmailError("Could not reach the SMTP server. Verify its host, port, firewall, DNS, and outbound network access.") from error
    except Exception as error:
        raise AccountEmailError("The account email could not be delivered. Verify SMTP connectivity and configuration.") from error
