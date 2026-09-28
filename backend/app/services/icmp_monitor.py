import asyncio
import os
import platform
import re
import subprocess
import structlog
from time import monotonic

from app.config import get_settings

logger = structlog.get_logger()
_icmp_process_limit = asyncio.Semaphore(max(1, get_settings().ICMP_PROCESS_CONCURRENCY))
_error_log_state = {"last": 0.0, "suppressed": 0}

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None


def _descriptor_capacity_available() -> bool:
    """Keep enough descriptors for the API and database before spawning ping."""
    if resource is None or not os.path.isdir("/proc/self/fd"):
        return True
    try:
        soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft_limit <= 0 or soft_limit == resource.RLIM_INFINITY:
            return True
        open_count = len(os.listdir("/proc/self/fd"))
        reserve = max(32, min(256, soft_limit // 10))
        return open_count + 3 < soft_limit - reserve
    except OSError:
        return False


def _probe_error(code: str) -> dict:
    now = monotonic()
    if now - _error_log_state["last"] >= 60:
        logger.warning("icmp_probe_unavailable", code=code,
                       suppressed=_error_log_state["suppressed"])
        _error_log_state.update(last=now, suppressed=0)
    else:
        _error_log_state["suppressed"] += 1
    return {"is_up": None, "latency_ms": None, "packet_loss_pct": None,
            "probe_valid": False, "error_code": code}


def _run_ping_sync(ip_address: str, count: int, timeout: float):
    is_win = platform.system().lower() == "windows"
    param = "-n" if is_win else "-c"
    timeout_param = "-w" if is_win else "-W"
    timeout_val = str(int(timeout * 1000)) if is_win else str(int(timeout))

    cmd = ["ping", param, str(count), timeout_param, timeout_val, ip_address]
    
    # Use standard subprocess.run to avoid Windows asyncio SelectorEventLoop NotImplementedError
    res = subprocess.run(cmd, capture_output=True, timeout=timeout + 3.0)
    return res.returncode, res.stdout, res.stderr


async def _run_ping_async(ip_address: str, count: int, timeout: float):
    cmd = ["ping", "-c", str(count), "-W", str(max(1, int(timeout))), ip_address]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout * count + 3.0)
    except BaseException:
        # Cancellation, timeout and unexpected runtime errors must never leave
        # a child or its pipe attached to the long-running collector process.
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.shield(process.communicate())
        except (ProcessLookupError, RuntimeError):
            pass
        raise
    return process.returncode, stdout, b""


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
        async with _icmp_process_limit:
            if not _descriptor_capacity_available():
                return _probe_error("DESCRIPTOR_PRESSURE")
            if is_win:
                returncode, stdout_bytes, stderr_bytes = await asyncio.to_thread(
                    _run_ping_sync, ip_address, count, timeout
                )
            else:
                returncode, stdout_bytes, stderr_bytes = await _run_ping_async(
                    ip_address, count, timeout
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
        # Linux iputils uses 1 for no replies and >1 for local execution
        # errors. Never translate a collector/runtime failure into an outage.
        if not is_win and returncode not in {0, 1}:
            return _probe_error("PING_EXECUTION_FAILED")
        is_up = returncode == 0

        # If ping succeeded but its localized loss line was not recognized,
        # avoid reporting a contradictory 100% loss for an online device.
        if is_up and packet_loss == 100.0:
            packet_loss = 0.0

        return {
            "is_up": is_up,
            "latency_ms": avg_latency if is_up else None,
            "packet_loss_pct": packet_loss if is_up else 100.0,
            "probe_valid": True,
            "error_code": None,
        }

    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return _probe_error("PING_TIMEOUT")
    except OSError as exc:
        return _probe_error("DESCRIPTOR_EXHAUSTED" if exc.errno in {23, 24} else "PING_OS_ERROR")
    except Exception:
        return _probe_error("PING_EXECUTION_FAILED")
