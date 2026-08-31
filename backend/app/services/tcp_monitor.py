import asyncio
import time
import structlog

logger = structlog.get_logger()


async def check_tcp_port(ip_address: str, port: int, timeout: float = 3.0) -> dict:
    """
    Checks if a TCP port is open and accepting connections.
    Returns dict: { is_up: bool, response_time_ms: float | None }
    """
    if not ip_address or not port:
        return {"is_up": False, "response_time_ms": None}

    start_time = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_address, port),
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        writer.close()
        await writer.wait_closed()

        return {
            "is_up": True,
            "response_time_ms": round(elapsed_ms, 2),
        }
    except Exception as e:
        logger.debug("tcp_check_failed", ip=ip_address, port=port, error=str(e))
        return {
            "is_up": False,
            "response_time_ms": None,
        }
