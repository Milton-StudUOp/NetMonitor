from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CapabilityResult:
    operating_system: str | None
    powershell_version: str | None
    provider_mode: str
    capabilities: dict[str, bool]
    diagnostics: dict = field(default_factory=dict)


class MonitoringProvider(ABC):
    @abstractmethod
    async def detect_capabilities(self) -> CapabilityResult: ...

    @abstractmethod
    async def discover_services(self) -> list[dict]: ...

    @abstractmethod
    async def check_services(self, names: list[str]) -> dict[str, str]: ...

    @abstractmethod
    async def collect_system_metrics(self) -> dict: ...

    @abstractmethod
    async def discover_metric_capabilities(self) -> dict[str, dict]: ...
