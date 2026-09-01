import asyncio
import platform
import re
import subprocess
import structlog

logger = structlog.get_logger()


def _run_ping_sync(ip_address: str, count: int, timeout: float):
    is_win = platform.system().lower() == "windows"
    param = "-n" if is_win else "-c"
    timeout_param = "-w" if is_win else "-W"
    timeout_val = str(int(timeout * 1000)) if is_win else str(int(timeout))

    cmd = ["ping", param, str(count), timeout_param, timeout_val, ip_address]
    
    # Use standard subprocess.run to avoid Windows asyncio SelectorEventLoop NotImplementedError
    res = subprocess.run(cmd, capture_output=True, timeout=timeout + 3.0)
    return res.returncode, res.stdout, res.stderr


async def ping_target(ip_address: str, count: int = 2, timeout: float = 2.0) -> dict:
    """
    Executes ICMP ping probe asynchronously using threadpool subprocess execution.
    Compatible with all Windows & Linux asyncio event loops without NotImplementedError.
    Returns dict: { is_up: bool, latency_ms: float | None, packet_loss_pct: float }
    """
    if not ip_address or not ip_address.strip():
        return {"is_up": False, "latency_ms": None, "packet_loss_pct": 100.0}

    ip_address = ip_address.strip()
    is_win = platform.system().lower() == "windows"

    try:
        returncode, stdout_bytes, stderr_bytes = await asyncio.to_thread(
            _run_ping_sync, ip_address, count, timeout
        )

        # Safely decode output using appropriate encoding for Windows/Linux
        output = ""
        for encoding in ["utf-8", "cp850", "cp1252", "latin1"]:
            try:
                output = stdout_bytes.decode(encoding)
                if output:
                    break
            except UnicodeDecodeError:
                continue

        if not output:
            output = stdout_bytes.decode("utf-8", errors="ignore")

        # Parse Packet Loss & Latency
        packet_loss = 100.0
        avg_latency = None

        if is_win:
            # Match percentage loss: (0% loss), (0% de perda), (0% perda)
            loss_match = (
                re.search(r"\((\d+)%\s*(?:de\s+)?perda\)", output, re.IGNORECASE)
                or re.search(r"\((\d+)%\s*loss\)", output, re.IGNORECASE)
                or re.search(r"(\d+)%\s*(?:de\s+)?perda", output, re.IGNORECASE)
                or re.search(r"(\d+)%\s*loss", output, re.IGNORECASE)
            )
            if loss_match:
                packet_loss = float(loss_match.group(1))

            # Match average latency: Média = 4ms, Media = 4ms, Average = 4ms, time=4ms
            avg_match = (
                re.search(r"M[eé]dia\s*=\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
                or re.search(r"Average\s*=\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
                or re.search(r"tempo[=<]\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
                or re.search(r"time[=<]\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
            )
            if avg_match:
                avg_latency = float(avg_match.group(1))
        else:
            # Parsing Linux ping output
            loss_match = re.search(r"(\d+)% packet loss", output, re.IGNORECASE)
            if loss_match:
                packet_loss = float(loss_match.group(1))

            rtt_match = re.search(r"rtt min/avg/max/mdev = [\d\.]+/([\d\.]+)/", output)
            if rtt_match:
                avg_latency = float(rtt_match.group(1))

        # Check for reply text or successful returncode
        has_reply = bool(
            re.search(r"resposta de", output, re.IGNORECASE)
            or re.search(r"reply from", output, re.IGNORECASE)
            or re.search(r"bytes=", output, re.IGNORECASE)
            or re.search(r"bytes from", output, re.IGNORECASE)
        )

        # A successful ping process is the portable availability signal. The
        # output is localized on some Linux distributions, so textual matches
        # are used only to extract metrics, not to decide whether the host is up.
        is_up = returncode == 0

        # If ping succeeded but its localized loss line was not recognized,
        # avoid reporting a contradictory 100% loss for an online device.
        if is_up and packet_loss == 100.0:
            packet_loss = 0.0

        return {
            "is_up": is_up,
            "latency_ms": avg_latency if is_up else None,
            "packet_loss_pct": packet_loss if is_up else 100.0,
        }

    except Exception as e:
        err_msg = str(e) or repr(e)
        logger.warning("icmp_ping_error", ip=ip_address, error=err_msg)
        return {"is_up": False, "latency_ms": None, "packet_loss_pct": 100.0}
