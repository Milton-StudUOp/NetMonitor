import json

from sqlalchemy import select

from app.models.monitoring_provider import DeviceCapability, DeviceMonitoringCredential
from app.security import decrypt_secret
from app.services.linux_monitoring import LinuxMonitoringError, LinuxMonitoringProvider, SSHTransport
from app.services.snmp_monitoring import SNMPMonitoringProvider, SNMPSecurity, SNMPTransport
from app.services.windows_monitoring import WinRMTransport, WindowsMonitoringProvider


async def provider_for_device(db, device, preferred: str | None = None):
    query = select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device.id,
        DeviceMonitoringCredential.enabled.is_(True))
    credentials = (await db.execute(query)).scalars().all()
    by_provider = {item.provider.upper():item for item in credentials}
    provider_name = preferred.upper() if preferred else await configured_provider(db, device.id, by_provider)
    credential = by_provider.get(provider_name)
    if not credential:
        raise LinuxMonitoringError("PROVIDER_NOT_CONFIGURED", "Configure remote monitoring for this device first")
    secret = decrypt_secret(credential.encrypted_password)
    if not secret:
        raise LinuxMonitoringError("CREDENTIAL_UNAVAILABLE", "Stored monitoring credentials cannot be decrypted")
    if provider_name == "LINUX":
        capability = (await db.execute(select(DeviceCapability).where(
            DeviceCapability.device_id == device.id, DeviceCapability.provider == "LINUX"))).scalar_one_or_none()
        host_key = (capability.diagnostics or {}).get("host_key") if capability else None
        return LinuxMonitoringProvider(SSHTransport(device.ip_address, credential.username, secret,
            credential.port, credential.authentication, host_key, credential.verify_certificate)), provider_name
    if provider_name == "SNMP":
        config = credential.configuration or {}
        try:
            snmp_secret = json.loads(secret)
        except (TypeError, ValueError):
            snmp_secret = {"community": secret}
        security = SNMPSecurity(version=config.get("version", "2c"),
            community=snmp_secret.get("community") if config.get("version", "2c").lower() != "3" else None,
            username=credential.username or config.get("username"), auth_key=snmp_secret.get("auth_key"),
            priv_key=snmp_secret.get("priv_key"), auth_protocol=config.get("auth_protocol", "SHA"),
            priv_protocol=config.get("priv_protocol", "AES"))
        return SNMPMonitoringProvider(SNMPTransport(device.ip_address, security, credential.port)), provider_name
    return WindowsMonitoringProvider(WinRMTransport(device.ip_address, credential.username, secret,
        credential.port, credential.use_https, credential.verify_certificate, credential.authentication)), provider_name


async def configured_provider(db, device_id: int, by_provider: dict | None = None) -> str:
    capabilities = (await db.execute(select(DeviceCapability).where(
        DeviceCapability.device_id == device_id, DeviceCapability.last_status == "READY")
        .order_by(DeviceCapability.discovered_at.desc()))).scalars().all()
    if capabilities and (not by_provider or capabilities[0].provider in by_provider):
        return capabilities[0].provider
    if by_provider:
        if len(by_provider) == 1: return next(iter(by_provider))
        if "WINDOWS" in by_provider: return "WINDOWS"
        if "LINUX" in by_provider: return "LINUX"
        if "SNMP" in by_provider: return "SNMP"
    return "WINDOWS"
