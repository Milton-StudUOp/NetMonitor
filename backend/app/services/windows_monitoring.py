import asyncio
import json

from app.services.monitoring_providers import CapabilityResult, MonitoringProvider


class WindowsMonitoringError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class WinRMTransport:
    def __init__(self, host: str, username: str, password: str, port: int = 5986,
                 use_https: bool = True, verify_certificate: bool = True,
                 authentication: str = "NTLM", timeout: int = 20):
        scheme = "https" if use_https else "http"
        self.endpoint = f"{scheme}://{host}:{port}/wsman"
        self.username, self.password = username, password
        self.authentication = authentication.lower()
        self.verify_certificate = verify_certificate
        self.timeout = timeout

    def _run_sync(self, script: str) -> str:
        try:
            import winrm
        except ImportError as exc:
            raise WindowsMonitoringError("PROVIDER_UNAVAILABLE", "Windows monitoring support is not installed") from exc
        try:
            session = winrm.Session(self.endpoint, auth=(self.username, self.password),
                transport=self.authentication,
                server_cert_validation="validate" if self.verify_certificate else "ignore",
                read_timeout_sec=self.timeout, operation_timeout_sec=max(5, self.timeout - 2))
            result = session.run_ps(script)
        except Exception as exc:
            name = type(exc).__name__.lower(); message = str(exc).lower()
            if "401" in message or "unauthorized" in message or "auth" in name:
                code, safe = "AUTHENTICATION_FAILED", "Credentials were rejected"
            elif "403" in message or "access is denied" in message:
                code, safe = "PERMISSION_DENIED", "The account lacks monitoring permissions"
            elif "timeout" in message:
                code, safe = "CHECK_TIMEOUT", "Windows monitoring timed out"
            else:
                code, safe = "WINRM_UNAVAILABLE", "Windows remote management is unavailable"
            raise WindowsMonitoringError(code, safe) from exc
        if result.status_code != 0:
            raise WindowsMonitoringError("DISCOVERY_FAILED", "Windows capability discovery failed")
        return result.std_out.decode("utf-8", errors="replace").strip()

    async def run_powershell(self, script: str) -> str:
        return await asyncio.wait_for(asyncio.to_thread(self._run_sync, script), self.timeout + 2)


class WindowsMonitoringProvider(MonitoringProvider):
    CAPABILITY_SCRIPT = r"""
$ErrorActionPreference='Stop'
$os=Get-WmiObject Win32_OperatingSystem
$ps=if($PSVersionTable){$PSVersionTable.PSVersion.ToString()}else{'1.0'}
@{operating_system=$os.Caption; powershell_version=$ps} | ConvertTo-Json -Compress
"""

    def __init__(self, transport: WinRMTransport): self.transport = transport

    async def detect_capabilities(self) -> CapabilityResult:
        raw = await self.transport.run_powershell(self.CAPABILITY_SCRIPT)
        try: data = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise WindowsMonitoringError("DISCOVERY_FAILED", "Windows returned an invalid capability response") from exc
        version = str(data.get("powershell_version") or "1.0")
        try: major = int(version.split(".", 1)[0])
        except ValueError: major = 1
        return CapabilityResult(data.get("operating_system"), version,
            "MODERN_CIM" if major >= 3 else "LEGACY_WMI",
            {"services": True, "cpu": True, "memory": True, "storage": True,
             "network_interfaces": True, "processes": True},
            {"transport": "winrm_https" if self.transport.endpoint.startswith("https") else "winrm_http"})

    async def discover_services(self) -> list[dict]:
        raise NotImplementedError("Service discovery is implemented in Phase 2")
