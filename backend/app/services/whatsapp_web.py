import httpx

from app.config import get_settings


class WhatsAppWebConfigurationError(ValueError):
    """Raised when the internal whatsapp-web.js bridge is not configured."""


def whatsapp_web_connection() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    url = settings.WHATSAPP_WEB_SERVICE_URL.strip().rstrip("/")
    token = settings.WHATSAPP_WEB_SERVICE_TOKEN.strip()
    if not url or len(token) < 32 or "replace-with" in token:
        raise WhatsAppWebConfigurationError(
            "Configure WHATSAPP_WEB_SERVICE_URL and a unique WHATSAPP_WEB_SERVICE_TOKEN of at least 32 characters."
        )
    return url, {"Authorization": f"Bearer {token}"}


async def bridge_request(method: str, path: str, *, payload: dict | None = None, timeout: float = 15) -> dict:
    url, headers = whatsapp_web_connection()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, f"{url}{path}", headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


async def whatsapp_web_status() -> dict:
    return await bridge_request("GET", "/session")


async def whatsapp_web_start() -> dict:
    return await bridge_request("POST", "/session/start", timeout=30)


async def whatsapp_web_logout() -> dict:
    return await bridge_request("DELETE", "/session", timeout=30)


async def whatsapp_web_send(recipient: str, message: str) -> None:
    await bridge_request("POST", "/messages", payload={"recipient": recipient, "message": message}, timeout=30)
