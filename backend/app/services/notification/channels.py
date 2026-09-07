import asyncio
import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.models.platform import NotificationIntegration
from app.security import decrypt_secret, encrypt_secret
from app.services.tls import verified_tls_context


class NotificationConfigurationError(ValueError):
    """Raised when an integration is incomplete or internally inconsistent."""


def environment_email_integration() -> NotificationIntegration | None:
    """Build a non-persisted EMAIL integration from server settings."""
    settings = get_settings()
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        return None
    item = NotificationIntegration(provider="EMAIL", name="SMTP Email (server environment)", enabled=True)
    item.public_config = {
        "smtp_server": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "username": settings.SMTP_USER,
        "from_address": settings.SMTP_FROM,
        "recipients": settings.email_recipients,
        "tls": settings.SMTP_PORT == 587,
        "ssl": settings.SMTP_PORT == 465,
    }
    item.encrypted_secrets = encrypt_secret(json.dumps({"password": settings.SMTP_PASSWORD}))
    return item


def integration_credentials(item: NotificationIntegration) -> tuple[dict, dict]:
    config = item.public_config or {}
    try:
        secrets = json.loads(decrypt_secret(item.encrypted_secrets) or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise NotificationConfigurationError("Stored credentials could not be decrypted. Save them again.") from exc
    return config, secrets


def validate_integration(provider: str, config: dict, secrets: dict) -> None:
    provider = provider.upper()
    if provider == "EMAIL":
        required = {"SMTP server": config.get("smtp_server"), "sender": config.get("from_address")}
        recipients = config.get("recipients") or []
        if not isinstance(recipients, list) or not recipients:
            required["at least one recipient"] = None
        invalid_addresses = [address for address in [config.get("from_address"), *recipients]
            if address and "@" not in parseaddr(str(address))[1]]
        if invalid_addresses:
            raise NotificationConfigurationError("Sender and recipient addresses must be valid email addresses.")
        port = int(config.get("smtp_port", 587))
        if not 1 <= port <= 65535:
            raise NotificationConfigurationError("SMTP port must be between 1 and 65535.")
        if config.get("tls") and config.get("ssl"):
            raise NotificationConfigurationError("Choose either STARTTLS or implicit TLS, not both.")
        if config.get("username") and not secrets.get("password"):
            required["password"] = None
    elif provider == "TELEGRAM":
        chat_ids = config.get("chat_ids") or ([config.get("chat_id")] if config.get("chat_id") else [])
        required = {"bot token": secrets.get("bot_token"), "at least one Chat ID": chat_ids}
    elif provider == "WHATSAPP":
        recipients = config.get("recipients") or ([config.get("recipient")] if config.get("recipient") else [])
        required = {
            "API URL": config.get("api_url"), "API token": secrets.get("api_token"),
            "at least one recipient": recipients,
        }
        url = config.get("api_url")
        if url and urlparse(url).scheme not in {"http", "https"}:
            raise NotificationConfigurationError("WhatsApp API URL must use HTTP or HTTPS.")
    else:
        raise NotificationConfigurationError(f"Unsupported notification provider: {provider}.")

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise NotificationConfigurationError(f"Missing required configuration: {', '.join(missing)}.")


SEVERITY_PRESENTATION = {
    "CRITICAL": {"icon": "🚨", "color": "#dc2626", "label": "Critical"},
    "WARNING": {"icon": "⚠️", "color": "#d97706", "label": "Warning"},
    "INFORMATION": {"icon": "ℹ️", "color": "#2563eb", "label": "Information"},
}


def _event_label(value: str) -> str:
    return (value or "MONITORING_EVENT").replace("_", " ").title()


def recipient_targets(provider: str, config: dict, additional: list[str] | None = None) -> list[str]:
    if provider == "TELEGRAM":
        configured = config.get("chat_ids") or ([config.get("chat_id")] if config.get("chat_id") else [])
    elif provider == "WHATSAPP":
        configured = config.get("recipients") or ([config.get("recipient")] if config.get("recipient") else [])
    else:
        configured = config.get("recipients") or []
    return list(dict.fromkeys(str(value).strip() for value in [*configured, *(additional or [])] if str(value).strip()))


def build_notification_content(
    title: str, message: str, severity: str, context: dict | None = None,
) -> dict[str, str]:
    context = context or {}
    severity = severity.upper()
    presentation = SEVERITY_PRESENTATION.get(severity, SEVERITY_PRESENTATION["INFORMATION"])
    recovered = bool(context.get("recovery"))
    status = "RECOVERED" if recovered else "ACTIVE"
    status_icon = "✅" if recovered else presentation["icon"]
    status_color = "#059669" if recovered else presentation["color"]
    event = _event_label(context.get("event_type", "MONITORING_EVENT"))
    alert_id = context.get("alert_id")
    target = context.get("target") or "Infrastructure resource"
    root_cause = context.get("root_cause")
    occurred_at = context.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    incident = f"NM-{int(alert_id):06d}" if alert_id is not None else "Test notification"

    subject = f"[NetMonitor] [{status}] [{presentation['label']}] {title}"
    lines = [
        f"{status_icon} NETMONITOR {status}",
        "",
        f"Incident: {incident}",
        f"Severity: {presentation['label']}",
        f"Event: {event}",
        f"Target: {target}",
        f"Time (UTC): {occurred_at}",
        "",
        title,
        message,
    ]
    if root_cause:
        lines.extend(["", "Probable cause", str(root_cause)])
    lines.extend(["", "This message was generated automatically by NetMonitor."])
    plain = "\n".join(lines)

    cause_html = ""
    if root_cause:
        cause_html = f"""
          <div style="margin-top:18px;padding:14px 16px;background:#fff7ed;border-left:4px solid #f97316;border-radius:6px">
            <div style="font-size:12px;font-weight:700;color:#9a3412;text-transform:uppercase;letter-spacing:.05em">Probable cause</div>
            <div style="margin-top:6px;color:#431407;line-height:1.5">{escape(str(root_cause))}</div>
          </div>"""
    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.12)">
    <div style="padding:22px 26px;background:{status_color};color:#fff">
      <div style="font-size:12px;font-weight:700;letter-spacing:.1em">NETMONITOR · {status}</div>
      <h1 style="font-size:21px;line-height:1.3;margin:8px 0 0">{status_icon} {escape(title)}</h1>
    </div>
    <div style="padding:24px 26px">
      <table role="presentation" style="width:100%;border-collapse:collapse;font-size:14px">
        <tr><td style="padding:7px 0;color:#64748b;width:130px">Incident</td><td style="padding:7px 0;font-weight:700">{incident}</td></tr>
        <tr><td style="padding:7px 0;color:#64748b">Severity</td><td style="padding:7px 0;font-weight:700;color:{presentation['color']}">{presentation['label']}</td></tr>
        <tr><td style="padding:7px 0;color:#64748b">Event</td><td style="padding:7px 0">{escape(event)}</td></tr>
        <tr><td style="padding:7px 0;color:#64748b">Target</td><td style="padding:7px 0">{escape(str(target))}</td></tr>
        <tr><td style="padding:7px 0;color:#64748b">Time (UTC)</td><td style="padding:7px 0">{escape(str(occurred_at))}</td></tr>
      </table>
      <div style="margin-top:20px;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;line-height:1.6">{escape(message)}</div>
      {cause_html}
    </div>
    <div style="padding:14px 26px;background:#0f172a;color:#94a3b8;font-size:11px">Automated infrastructure monitoring notification · NetMonitor</div>
  </div>
</body></html>"""
    return {"subject": subject, "plain": plain, "html": html}


async def send_notification(
    item: NotificationIntegration, title: str, message: str, severity: str,
    additional_recipients: list[str] | None = None, context: dict | None = None,
) -> None:
    config, secrets = integration_credentials(item)
    config = dict(config)
    if item.provider == "TELEGRAM":
        config["chat_ids"] = recipient_targets("TELEGRAM", config, additional_recipients)
    elif item.provider == "WHATSAPP":
        config["recipients"] = recipient_targets("WHATSAPP", config, additional_recipients)
    else:
        config["recipients"] = recipient_targets("EMAIL", config, additional_recipients)
    validate_integration(item.provider, config, secrets)
    content = build_notification_content(title, message, severity, context)
    text = content["plain"]

    if item.provider == "TELEGRAM":
        targets = recipient_targets("TELEGRAM", config, additional_recipients)
        async with httpx.AsyncClient(timeout=10) as client:
            for target in targets:
                response = await client.post(
                    f"https://api.telegram.org/bot{secrets['bot_token']}/sendMessage",
                    json={"chat_id": target, "text": text[:4000]},
                )
                response.raise_for_status()
        return

    if item.provider == "WHATSAPP":
        targets = recipient_targets("WHATSAPP", config, additional_recipients)
        async with httpx.AsyncClient(timeout=10) as client:
            for target in targets:
                response = await client.post(
                    config["api_url"],
                    headers={"Authorization": f"Bearer {secrets['api_token']}"},
                    json={"sender": config.get("sender_id"), "recipient": target, "message": text},
                )
                response.raise_for_status()
        return

    mail = EmailMessage()
    mail["Subject"] = content["subject"]
    mail["From"] = config["from_address"]
    recipients = recipient_targets("EMAIL", config, additional_recipients)
    mail["To"] = ", ".join(recipients)
    mail.set_content(text)
    mail.add_alternative(content["html"], subtype="html")

    def send_email() -> None:
        smtp_class = smtplib.SMTP_SSL if config.get("ssl") else smtplib.SMTP
        smtp_kwargs = {"timeout": 10}
        if config.get("ssl"):
            smtp_kwargs["context"] = verified_tls_context()
        with smtp_class(config["smtp_server"], int(config.get("smtp_port", 587)), **smtp_kwargs) as smtp:
            if config.get("tls") and not config.get("ssl"):
                smtp.starttls(context=verified_tls_context())
            if config.get("username"):
                smtp.login(config["username"], secrets["password"])
            smtp.send_message(mail)

    await asyncio.to_thread(send_email)


def safe_delivery_error(exc: Exception) -> str:
    if isinstance(exc, NotificationConfigurationError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Provider returned HTTP {exc.response.status_code}. Verify credentials and recipient settings."
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "Connection timed out. Verify the provider address and outbound network access."
    if isinstance(exc, (httpx.NetworkError, OSError, smtplib.SMTPException)):
        return "Could not connect or authenticate. Verify the server, credentials, TLS mode, and network access."
    return "Notification delivery failed. Review the integration configuration and backend logs."
