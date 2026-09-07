import time
import aiohttp
import structlog

logger = structlog.get_logger()


async def check_http_endpoint(
    url: str, expected_status: int = 200, timeout: float = 5.0
) -> dict:
    """
    Performs HTTP GET probe to test application-level service availability.
    Returns dict: { is_up: bool, status_code: int | None, response_time_ms: float | None }
    """
    if not url:
        return {"is_up": False, "status_code": None, "response_time_ms": None}

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"

    start_time = time.perf_counter()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                is_up = response.status == expected_status
                return {
                    "is_up": is_up,
                    "status_code": response.status,
                    "response_time_ms": round(elapsed_ms, 2),
                }
    except Exception as e:
        logger.debug("http_check_failed", error_type=type(e).__name__)
        return {
            "is_up": False,
            "status_code": None,
            "response_time_ms": None,
        }
