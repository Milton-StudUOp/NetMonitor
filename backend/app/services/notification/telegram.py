import aiohttp
import structlog
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


async def send_telegram_alert(title: str, message: str, severity: str) -> bool:
    """Sends Telegram Bot API alert message."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.debug("telegram_alert_skipped_not_configured")
        return False

    emoji = "🚨" if severity == "CRITICAL" else ("⚠️" if severity == "WARNING" else "ℹ️")
    text = f"{emoji} *[{severity.upper()}] {title}*\n\n{message}"

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5.0) as resp:
                if resp.status == 200:
                    logger.info("telegram_alert_sent", title=title)
                    return True
                logger.warning("telegram_alert_http_error", status=resp.status)
                return False
    except Exception as e:
        logger.error("telegram_alert_failed", error=str(e))
        return False
