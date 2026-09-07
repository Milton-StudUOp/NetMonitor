import aiohttp
import structlog
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


async def send_teams_alert(title: str, message: str, severity: str) -> bool:
    """Sends Microsoft Teams webhook Adaptive Card alert."""
    if not settings.TEAMS_WEBHOOK_URL:
        logger.debug("teams_alert_skipped_no_webhook")
        return False

    color = "FF0000" if severity == "CRITICAL" else ("FFA500" if severity == "WARNING" else "0078D7")

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "sections": [
            {
                "activityTitle": f"[{severity.upper()}] {title}",
                "activitySubtitle": "Network Monitor Alert",
                "text": message,
                "markdown": True,
            }
        ],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(settings.TEAMS_WEBHOOK_URL, json=card, timeout=5.0) as resp:
                if resp.status in (200, 204):
                    logger.info("teams_alert_sent")
                    return True
                logger.warning("teams_alert_http_error", status=resp.status)
                return False
    except Exception as e:
        logger.error("teams_alert_failed", error_type=type(e).__name__)
        return False
