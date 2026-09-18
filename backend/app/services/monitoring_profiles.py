from sqlalchemy import select

from app.database import async_session_factory
from app.models.monitoring_provider import MonitoringProfile

BUILTIN_PROFILES = [
    ("Windows Server — Standard", ["EventLog", "LanmanServer", "WinRM", "W32Time"], "Core Windows services"),
    ("Database Server", ["MSSQL*", "SQLSERVERAGENT*", "MySQL*", "OracleService*"], "Common database services"),
    ("OCC Server", ["*OCC*", "MSSQL*"], "OCC application and database services"),
    ("Critical Infrastructure", ["*"], "All discovered services; review selection after applying"),
]


async def ensure_builtin_profiles():
    async with async_session_factory() as db:
        existing = set((await db.execute(select(MonitoringProfile.name))).scalars().all())
        for name, patterns, description in BUILTIN_PROFILES:
            if name not in existing:
                db.add(MonitoringProfile(name=name, description=description, service_patterns=patterns,
                    metric_config={"cpu": True, "memory": True, "storage": True},
                    defaults={"expected_state": "running", "check_interval": 60, "failure_threshold": 1,
                        "recovery_threshold": 2, "severity": "CRITICAL", "notifications_enabled": True}))
        await db.commit()
