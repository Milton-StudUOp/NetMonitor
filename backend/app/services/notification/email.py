import structlog
from app.config import get_settings
from app.services.tls import verified_tls_context

logger = structlog.get_logger()
settings = get_settings()


async def send_email_alert(title: str, message: str, severity: str) -> bool:
    """Sends email alert asynchronously via aiosmtplib if configured."""
    if not settings.SMTP_HOST or not settings.email_recipients:
        logger.debug("email_alert_skipped_not_configured")
        return False

    try:
        import aiosmtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = ", ".join(settings.email_recipients)
        msg["Subject"] = f"[{severity.upper()}] {title}"
        msg.set_content(f"{title}\n\n{message}\n\n--- Network Monitor Alert System ---")

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=True,
            tls_context=verified_tls_context(),
            timeout=5.0,
        )
        logger.info("email_alert_sent")
        return True
    except Exception as e:
        logger.error("email_alert_failed", error_type=type(e).__name__)
        return False
