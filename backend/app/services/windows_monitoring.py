import asyncio
import json

from app.services.monitoring_providers import CapabilityResult, MonitoringProvider, MonitoringProviderError


class WindowsMonitoringError(MonitoringProviderError):
    pass


def classify_winrm_error(exc: Exception) -> tuple[str, str]:
    """Return a safe, actionable classification without exposing transport details."""
    name, message = type(exc).__name__.lower(), str(exc).lower()
    if any(value in message for value in ("certificate verify failed", "certificate validation", "self signed certificate", "ssl: cert")):
        return "TLS_CERTIFICATE_INVALID", "The WinRM TLS certificate is not trusted"
    if "401" in message or "unauthorized" in message or "auth" in name:
        return "AUTHENTICATION_FAILED", "Credentials were rejected"
    if "403" in message or "access is denied" in message:
        return "PERMISSION_DENIED", "The account lacks monitoring permissions"
    if "timeout" in message:
        return "CHECK_TIMEOUT", "Windows monitoring timed out"
    return "WINRM_UNAVAILABLE", "Windows remote management is unavailable"


def classify_powershell_error(output: bytes | str | None) -> tuple[str, str]:
    message = (output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output or "")).lower()
    if "access is denied" in message or "unauthorizedaccessexception" in message:
        return "PERMISSION_DENIED", "The account lacks permission to query Windows management data"
    if "not recognized" in message or "commandnotfoundexception" in message:
        return "PROVIDER_UNAVAILABLE", "The target does not provide the required Windows management commands"
    if "invalid class" in message or "invalid namespace" in message:
        return "CAPABILITY_UNAVAILABLE", "The target does not expose a required Windows management class"
    return "DISCOVERY_FAILED", "Windows remote command failed"


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
            code, safe = classify_winrm_error(exc)
            raise WindowsMonitoringError(code, safe) from exc
        if result.status_code != 0:
            code, safe = classify_powershell_error(result.std_err)
            raise WindowsMonitoringError(code, safe)
        return result.std_out.decode("utf-8", errors="replace").strip()

    async def run_powershell(self, script: str) -> str:
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._run_sync, script), self.timeout + 2)
        except TimeoutError as exc:
            raise WindowsMonitoringError("CHECK_TIMEOUT", "Windows monitoring timed out") from exc


class WindowsMonitoringProvider(MonitoringProvider):
    CAPABILITY_SCRIPT = r"""
$ErrorActionPreference='Stop'
$hasCim=[bool](Get-Command Get-CimClass -ErrorAction SilentlyContinue)
$hasWmi=[bool](Get-Command Get-WmiObject -ErrorAction SilentlyContinue)
if(-not $hasCim -and -not $hasWmi){throw 'No Windows management cmdlet is available'}
$ps=if($PSVersionTable){$PSVersionTable.PSVersion.ToString()}else{'1.0'}
$classes=@{}
foreach($item in @('Win32_Service','Win32_Processor','Win32_OperatingSystem','Win32_LogicalDisk','Win32_NetworkAdapterConfiguration','Win32_PerfFormattedData_PerfProc_Process','Win32_NTLogEvent')){
  try{
    if($hasCim){$null=Get-CimClass -ClassName $item -ErrorAction Stop}
    else{$null=Get-WmiObject -List -Class $item -ErrorAction Stop}
    $classes[$item]=$true
  }catch{$classes[$item]=$false}
}
$mode=if($hasCim){'MODERN_CIM'}else{'LEGACY_WMI'}
@{operating_system=$env:OS;powershell_version=$ps;mode=$mode;classes=$classes} | ConvertTo-Json -Compress -Depth 4
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
        classes = data.get("classes") or {}
        available = lambda name, default=False: bool(classes.get(name, default))
        return CapabilityResult(data.get("operating_system"), version,
            data.get("mode") or ("MODERN_CIM" if major >= 3 else "LEGACY_WMI"),
            {"services": available("Win32_Service", True),
             "cpu": available("Win32_Processor"),
             "memory": available("Win32_OperatingSystem"),
             "uptime": available("Win32_OperatingSystem"),
             "storage": available("Win32_LogicalDisk"),
             "network_interfaces": available("Win32_NetworkAdapterConfiguration"),
             "processes": available("Win32_PerfFormattedData_PerfProc_Process"),
             "system_information": available("Win32_OperatingSystem"),
             "events": available("Win32_NTLogEvent")},
            {"transport": "winrm_https" if self.transport.endpoint.startswith("https") else "winrm_http"})

    async def discover_metric_capabilities(self) -> dict[str, dict]:
        detected = await self.detect_capabilities()
        labels = {"cpu":"CPU usage", "memory":"Memory usage", "uptime":"System uptime",
            "storage":"Disk usage and free space", "network_interfaces":"Network interfaces and traffic",
            "processes":"Top processes", "system_information":"Windows system information",
            "events":"Recent critical Windows events"}
        return {key: {"supported": supported, "label": labels[key]} for key, supported in
            detected.capabilities.items() if key != "services"}

    async def discover_services(self) -> list[dict]:
        raw = await self.transport.run_powershell(r"""
$ErrorActionPreference='Stop'
Get-WmiObject Win32_Service | Select-Object Name,DisplayName,State,StartMode,Description,StartName | ConvertTo-Json -Compress
""")
        try: values = json.loads(raw or "[]")
        except ValueError as exc: raise WindowsMonitoringError("DISCOVERY_FAILED", "Windows returned an invalid service inventory") from exc
        if isinstance(values, dict): values = [values]
        return [{"name": str(x.get("Name") or ""), "display_name": str(x.get("DisplayName") or x.get("Name") or ""),
            "state": str(x.get("State") or "unknown").lower(), "start_mode": str(x.get("StartMode") or "unknown").lower(),
            "description": x.get("Description"), "service_account": x.get("StartName"), "monitoring_provider": "windows"}
            for x in values if x.get("Name")]

    async def check_services(self, names: list[str]) -> dict[str, str]:
        if not names: return {}
        encoded = json.dumps(names).replace("'", "''")
        raw = await self.transport.run_powershell("$names=ConvertFrom-Json '" + encoded + "'; "
            "Get-WmiObject Win32_Service | Where-Object {$names -contains $_.Name} | "
            "Select-Object Name,State | ConvertTo-Json -Compress")
        try: values = json.loads(raw or "[]")
        except ValueError as exc: raise WindowsMonitoringError("DISCOVERY_FAILED", "Windows returned an invalid service status response") from exc
        if isinstance(values, dict): values = [values]
        return {str(x["Name"]): str(x.get("State") or "unknown").lower() for x in values}

    async def collect_system_metrics(self) -> dict:
        core_raw = await self.transport.run_powershell(r"""
$ErrorActionPreference='Stop';$os=Get-WmiObject Win32_OperatingSystem;$cpu=(Get-WmiObject Win32_Processor|Measure-Object LoadPercentage -Average).Average;$computer=Get-WmiObject Win32_ComputerSystem;$disks=@(Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3"|%{@{name=$_.DeviceID;label=$_.VolumeName;file_system=$_.FileSystem;size_bytes=[int64]$_.Size;free_bytes=[int64]$_.FreeSpace;used_percent=if($_.Size){[math]::Round((1-($_.FreeSpace/$_.Size))*100,2)}else{0}}});$boot=$os.ConvertToDateTime($os.LastBootUpTime);@{cpu_percent=[double]$cpu;memory_percent=[math]::Round((1-($os.FreePhysicalMemory/$os.TotalVisibleMemorySize))*100,2);uptime_seconds=[int64]((Get-Date)-$boot).TotalSeconds;storage=$disks;system_information=@{caption=$os.Caption;version=$os.Version;architecture=$os.OSArchitecture;computer_name=$os.CSName;manufacturer=$computer.Manufacturer;model=$computer.Model;last_boot=$os.LastBootUpTime}}|ConvertTo-Json -Compress -Depth 5
""")
        scripts = {
            "network": r"""$ErrorActionPreference='Stop';$net=@(Get-WmiObject Win32_NetworkAdapter|%{$s=if($_.NetConnectionStatus-eq 2){'up'}elseif($_.NetConnectionStatus-in 0,1,4,5,6,7){'down'}else{'unknown'};@{index=[int]$_.InterfaceIndex;name=if($_.NetConnectionID){$_.NetConnectionID}else{$_.Name};description=$_.Description;status=$s;mac_address=$_.MACAddress}});$cfg=@(Get-WmiObject Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True"|%{@{description=$_.Description;mac_address=$_.MACAddress;ip_addresses=@($_.IPAddress);gateways=@($_.DefaultIPGateway)}});@{network_interfaces=$net;network_adapters=$cfg}|ConvertTo-Json -Compress -Depth 5""",
            "processes": r"""$ErrorActionPreference='Stop';@(Get-WmiObject Win32_PerfFormattedData_PerfProc_Process|?{$_.Name-ne'_Total'-and$_.Name-ne'Idle'}|Sort PercentProcessorTime -Descending|Select -First 20|%{@{name=$_.Name;process_id=[int]$_.IDProcess;cpu_percent=[double]$_.PercentProcessorTime;working_set_bytes=[int64]$_.WorkingSetPrivate}})|ConvertTo-Json -Compress""",
            "events": r"""$ErrorActionPreference='Stop';@(Get-WmiObject Win32_NTLogEvent -Filter "Logfile='System' AND (EventType=1 OR EventType=2)"|Select -First 20|%{@{source=$_.SourceName;event_code=[int]$_.EventCode;type=[int]$_.EventType;message=$_.Message;time_generated=$_.TimeGenerated}})|ConvertTo-Json -Compress -Depth 3""",
        }
        try:
            result = json.loads(core_raw)
        except (ValueError, TypeError) as exc:
            raise WindowsMonitoringError("DISCOVERY_FAILED", "Windows returned an invalid core metrics response") from exc

        async def optional(name: str, script: str):
            try:
                raw = await self.transport.run_powershell(script)
                return name, json.loads(raw or "[]")
            except (MonitoringProviderError, ValueError, TypeError):
                return name, []

        optional_results = await asyncio.gather(*(optional(name, script) for name, script in scripts.items()))
        values = dict(optional_results)
        network = values.get("network") if isinstance(values.get("network"), dict) else {}
        result["network_interfaces"] = network.get("network_interfaces", [])
        result["network_adapters"] = network.get("network_adapters", [])
        processes = values.get("processes", [])
        if isinstance(processes, dict):
            processes = processes.get("processes", [processes])
        events = values.get("events", [])
        if isinstance(events, dict):
            events = events.get("events", [events])
        result["processes"] = processes
        result["events"] = events
        return result
