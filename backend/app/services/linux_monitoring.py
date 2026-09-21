import asyncio
import json
import shlex

from app.services.monitoring_providers import CapabilityResult, MonitoringProvider, MonitoringProviderError


class LinuxMonitoringError(MonitoringProviderError):
    pass


class SSHTransport:
    """Restricted SSH transport. Callers can only execute backend-owned commands."""

    def __init__(self, host: str, username: str, secret: str, port: int = 22,
                 authentication: str = "SSH_PASSWORD", host_key: str | None = None,
                 verify_host_key: bool = True, timeout: int = 20):
        self.host, self.username, self.secret, self.port = host, username, secret, port
        self.authentication = authentication.upper()
        self.host_key, self.verify_host_key, self.timeout = host_key, verify_host_key, timeout
        self.observed_host_key: str | None = None

    async def run(self, command: str) -> str:
        try:
            import asyncssh
        except ImportError as exc:
            raise LinuxMonitoringError("PROVIDER_UNAVAILABLE", "Linux SSH monitoring support is not installed") from exc
        options = {"host": self.host, "port": self.port, "username": self.username,
            "known_hosts": None, "connect_timeout": self.timeout, "login_timeout": self.timeout}
        if self.authentication == "SSH_KEY":
            try: options["client_keys"] = [asyncssh.import_private_key(self.secret)]
            except Exception as exc: raise LinuxMonitoringError("AUTHENTICATION_FAILED", "The SSH private key is invalid") from exc
        else:
            options["password"] = self.secret
        try:
            async with asyncssh.connect(**options) as connection:
                server_key = connection.get_server_host_key()
                self.observed_host_key = server_key.export_public_key().decode("ascii").strip()
                if self.verify_host_key:
                    if not self.host_key:
                        raise LinuxMonitoringError("HOST_KEY_UNTRUSTED", "Confirm the SSH host key before saving this connection")
                    if self.host_key.strip() != self.observed_host_key:
                        raise LinuxMonitoringError("HOST_KEY_MISMATCH", "The SSH host identity differs from the trusted key")
                result = await asyncio.wait_for(connection.run(command, check=False), self.timeout)
        except LinuxMonitoringError:
            raise
        except asyncio.TimeoutError as exc:
            raise LinuxMonitoringError("CHECK_TIMEOUT", "Linux monitoring timed out") from exc
        except Exception as exc:
            name, message = type(exc).__name__.lower(), str(exc).lower()
            if "permission" in message or "auth" in name or "key" in name:
                code, safe = "AUTHENTICATION_FAILED", "SSH credentials were rejected"
            elif "host key" in message:
                code, safe = "HOST_KEY_MISMATCH", "The SSH host identity could not be verified"
            elif "timeout" in message:
                code, safe = "CHECK_TIMEOUT", "Linux monitoring timed out"
            else:
                code, safe = "SSH_UNAVAILABLE", "SSH remote management is unavailable"
            raise LinuxMonitoringError(code, safe) from exc
        if result.exit_status != 0:
            message = (result.stderr or "").lower()
            if "permission denied" in message:
                raise LinuxMonitoringError("PERMISSION_DENIED", "The account lacks monitoring permissions")
            raise LinuxMonitoringError("DISCOVERY_FAILED", "Linux returned an unsuccessful monitoring response")
        return result.stdout.strip()


class LinuxMonitoringProvider(MonitoringProvider):
    CAPABILITY_COMMAND = """sh -c 'printf "OS_BEGIN\\n"; cat /etc/os-release 2>/dev/null || true; printf "OS_END\\n"; uname -srmo; command -v systemctl || true; test -r /proc/stat && echo PROC_OK; test -r /sys/class/net && echo SYS_NET_OK; command -v df || true; command -v ip || true'"""
    METRICS_COMMAND = """sh -c 'printf "CPU1 "; head -1 /proc/stat; sleep 1; printf "CPU2 "; head -1 /proc/stat; printf "MEM_BEGIN\\n"; cat /proc/meminfo; printf "MEM_END\\nUPTIME "; cut -d" " -f1 /proc/uptime; printf "DF_BEGIN\\n"; df -P -B1 2>/dev/null; printf "DF_END\\nNET_BEGIN\\n"; for n in /sys/class/net/*; do i=${n##*/}; state=$(cat "$n/operstate" 2>/dev/null); carrier=$(cat "$n/carrier" 2>/dev/null); if [ "$state" = up ] || [ "$carrier" = 1 ]; then normalized=up; elif [ "$state" = down ] || [ "$state" = lowerlayerdown ] || [ "$state" = dormant ] || [ "$carrier" = 0 ]; then normalized=down; else normalized=unknown; fi; printf "%s|%s|" "$i" "$normalized"; cat "$n/address" 2>/dev/null | tr "\\n" "|"; cat "$n/statistics/rx_bytes" 2>/dev/null | tr "\\n" "|"; cat "$n/statistics/tx_bytes" 2>/dev/null; done; printf "NET_END\\nSYS_BEGIN\\n"; hostname; uname -srmo; cat /etc/os-release 2>/dev/null; printf "SYS_END\\nPROC_BEGIN\\n"; ps -eo pid=,pcpu=,rss=,comm= --sort=-pcpu 2>/dev/null | head -20; printf "PROC_END\\n"'"""
    SERVICE_DISCOVERY_COMMAND = """sh -c 'units=$(LC_ALL=C systemctl list-units --type=service --all --no-legend --plain --full 2>/dev/null | awk "{print \\$1}"); test -n "$units" || exit 0; systemctl show --no-pager --property=Id,Description,ActiveState,SubState,UnitFileState $units'"""

    def __init__(self, transport: SSHTransport): self.transport = transport

    async def detect_capabilities(self) -> CapabilityResult:
        raw = await self.transport.run(self.CAPABILITY_COMMAND)
        os_data = _section(raw, "OS_BEGIN", "OS_END")
        release = _key_values(os_data)
        systemd = "/systemctl" in raw
        proc = "PROC_OK" in raw
        sys_net = "SYS_NET_OK" in raw
        capabilities = {"services": systemd, "cpu": proc, "memory": proc, "uptime": proc,
            "storage": "\ndf\n" in f"\n{raw}\n" or "/df" in raw,
            "network_interfaces": sys_net, "processes": True, "system_information": True, "events": False}
        operating_system = release.get("PRETTY_NAME") or release.get("NAME") or "Linux"
        return CapabilityResult(operating_system, None, "SYSTEMD" if systemd else "LINUX_GENERIC",
            capabilities, {"transport": "ssh", "host_key": self.transport.observed_host_key,
                "distribution": release.get("ID"), "version": release.get("VERSION_ID")})

    async def discover_metric_capabilities(self) -> dict[str, dict]:
        detected = await self.detect_capabilities()
        labels = {"cpu":"CPU usage", "memory":"Memory usage", "uptime":"System uptime",
            "storage":"Disk usage and free space", "network_interfaces":"Network interfaces and traffic",
            "processes":"Top processes", "system_information":"Linux system information", "events":"System events"}
        return {key:{"supported":supported,"label":labels[key]} for key,supported in detected.capabilities.items() if key != "services"}

    async def discover_services(self) -> list[dict]:
        # `systemctl show` without explicit unit names reports manager
        # properties on several distributions. List units first, then request
        # their normalized properties in a single remote command.
        raw = await self.transport.run(self.SERVICE_DISCOVERY_COMMAND)
        services = []
        for block in raw.split("\n\n"):
            item = _key_values(block)
            name = item.get("Id")
            if not name: continue
            active, sub = item.get("ActiveState", "unknown"), item.get("SubState", "unknown")
            state = "running" if active == "active" else ("stopped" if active in {"inactive","failed","deactivating"} else active)
            services.append({"name":name, "display_name":item.get("Description") or name, "state":state,
                "start_mode":item.get("UnitFileState") or "unknown", "description":item.get("Description"),
                "service_account":None, "monitoring_provider":"linux"})
        return services

    async def check_services(self, names: list[str]) -> dict[str, str]:
        if not names: return {}
        safe_names = " ".join(shlex.quote(name) for name in names)
        raw = await self.transport.run(f"systemctl show --no-pager --property=Id,ActiveState,SubState -- {safe_names}")
        result = {}
        for block in raw.split("\n\n"):
            item = _key_values(block); name = item.get("Id")
            if name:
                result[name] = "running" if item.get("ActiveState") == "active" else ("stopped" if item.get("ActiveState") in {"inactive","failed","deactivating"} else item.get("ActiveState","unknown"))
        return result

    async def collect_system_metrics(self) -> dict:
        raw = await self.transport.run(self.METRICS_COMMAND)
        cpu1, cpu2 = _cpu_line(raw, "CPU1"), _cpu_line(raw, "CPU2")
        cpu_percent = _cpu_percent(cpu1, cpu2)
        memory = _key_values(_section(raw, "MEM_BEGIN", "MEM_END"), separator=":")
        total, available = _kb(memory.get("MemTotal")), _kb(memory.get("MemAvailable") or memory.get("MemFree"))
        storage = []
        for line in _section(raw, "DF_BEGIN", "DF_END").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                storage.append({"name":parts[0], "label":parts[5], "file_system":None,
                    "size_bytes":_int(parts[1]), "free_bytes":_int(parts[3]),
                    "used_percent":float(parts[4].rstrip("%")) if parts[4].rstrip("%").replace(".","").isdigit() else 0})
        interfaces = []
        for line in _section(raw, "NET_BEGIN", "NET_END").splitlines():
            parts = line.split("|")
            if len(parts) >= 5: interfaces.append({"name":parts[0], "status":parts[1], "mac_address":parts[2],
                "bytes_received":_int(parts[3]), "bytes_sent":_int(parts[4])})
        processes = []
        for line in _section(raw, "PROC_BEGIN", "PROC_END").splitlines():
            parts = line.split(None, 3)
            if len(parts) == 4: processes.append({"process_id":_int(parts[0]), "cpu_percent":_float(parts[1]),
                "working_set_bytes":_int(parts[2])*1024, "name":parts[3]})
        system_lines = _section(raw, "SYS_BEGIN", "SYS_END").splitlines()
        release = _key_values("\n".join(system_lines[2:]))
        uptime_line = next((line for line in raw.splitlines() if line.startswith("UPTIME ")), "UPTIME 0")
        return {"cpu_percent":cpu_percent, "memory_percent":round((1-available/total)*100,2) if total else None,
            "uptime_seconds":int(_float(uptime_line.split(None,1)[1])), "storage":storage,
            "network_interfaces":interfaces, "network_adapters":interfaces, "processes":processes,
            "system_information":{"computer_name":system_lines[0] if system_lines else None,
                "kernel":system_lines[1] if len(system_lines)>1 else None,
                "caption":release.get("PRETTY_NAME") or release.get("NAME"), "version":release.get("VERSION_ID")}, "events":[]}


def _section(value: str, start: str, end: str) -> str:
    if start not in value or end not in value: return ""
    return value.split(start,1)[1].split(end,1)[0].strip()

def _key_values(value: str, separator: str = "=") -> dict[str,str]:
    result = {}
    for line in value.splitlines():
        if separator in line:
            key,val=line.split(separator,1); result[key.strip()]=val.strip().strip('"')
    return result

def _cpu_line(raw: str, marker: str) -> list[int]:
    line=next((x for x in raw.splitlines() if x.startswith(marker+" ")),"")
    parts=line.split()[2:]
    return [_int(x) for x in parts]

def _cpu_percent(first: list[int], second: list[int]) -> float | None:
    if not first or len(first)!=len(second): return None
    total=sum(second)-sum(first); idle=(second[3]+(second[4] if len(second)>4 else 0))-(first[3]+(first[4] if len(first)>4 else 0))
    return round((total-idle)*100/total,2) if total>0 else 0

def _kb(value: str | None) -> int: return _int((value or "0").split()[0])*1024
def _int(value) -> int:
    try: return int(value)
    except (TypeError,ValueError): return 0
def _float(value) -> float:
    try: return float(value)
    except (TypeError,ValueError): return 0.0
