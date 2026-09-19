from datetime import datetime, timezone
from ipaddress import ip_address
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device, DeviceStatus
from app.models.link import Link, LinkPriority, LinkStatus, LinkType
from app.models.monitoring_provider import DeviceCapability, DeviceMonitoringCredential
from app.schemas.device import DeviceCreate, DeviceRead, DeviceUpdate, DeviceStatusRead
from app.schemas.monitoring_provider import (LinuxConnectionInput, LinuxConnectionRead, WindowsCapabilityRead,
    WindowsConnectionInput, WindowsConnectionRead)
from app.security import decrypt_secret, encrypt_secret
from app.services.windows_monitoring import WinRMTransport, WindowsMonitoringError, WindowsMonitoringProvider
from app.services.linux_monitoring import LinuxMonitoringError, LinuxMonitoringProvider, SSHTransport

router = APIRouter(prefix="/api/devices", tags=["Devices"])

AUTO_GATEWAY_LINK_DESCRIPTION = (
    "Enlace principal criado automaticamente a partir do equipamento gateway."
)


def _reject_loopback_windows_target(device: Device) -> None:
    try:
        loopback = ip_address(device.ip_address).is_loopback
    except ValueError:
        loopback = device.ip_address.lower() == "localhost"
    if loopback and os.name != "nt":
        raise HTTPException(status_code=400, detail=(
            "127.0.0.1/localhost points to the NetMonitor backend itself. "
            "Configure this device with the Windows host's reachable LAN address or DNS name."
        ))


def _auto_gateway_link_name(gateway: Device, device: Device) -> str:
    suffix = f" [{gateway.id}-{device.id}]"
    base = f"AUTO: {gateway.name} -> {device.name}"
    return f"{base[:128 - len(suffix)]}{suffix}"


async def _find_auto_gateway_link(db: AsyncSession, device_id: int) -> Link | None:
    result = await db.execute(
        select(Link).where(
            Link.destination_device_id == device_id,
            Link.description == AUTO_GATEWAY_LINK_DESCRIPTION,
        )
    )
    return result.scalar_one_or_none()


async def _create_auto_gateway_link(
    db: AsyncSession,
    device: Device,
    gateway: Device,
) -> Link:
    link = Link(
        name=_auto_gateway_link_name(gateway, device),
        description=AUTO_GATEWAY_LINK_DESCRIPTION,
        source_device_id=gateway.id,
        destination_device_id=device.id,
        link_type=LinkType.OTHER,
        priority=LinkPriority.PRIMARY,
        is_critical=device.is_critical,
        monitoring_interval=5,
    )
    db.add(link)
    await db.flush()
    return link


async def _validate_device_dependencies(
    db: AsyncSession,
    device_id: int | None,
    gateway_device_id: int | None,
    primary_link_id: int | None,
) -> None:
    if gateway_device_id is not None:
        if device_id is not None and gateway_device_id == device_id:
            raise HTTPException(status_code=400, detail="Device cannot use itself as gateway")
        if not await db.get(Device, gateway_device_id):
            raise HTTPException(status_code=400, detail="Gateway device not found")

    if primary_link_id is not None:
        if device_id is None:
            raise HTTPException(status_code=400, detail="Primary link can only be assigned after device creation")
        link = await db.get(Link, primary_link_id)
        if not link:
            raise HTTPException(status_code=400, detail="Primary link not found")
        if device_id is not None and device_id not in (link.source_device_id, link.destination_device_id):
            raise HTTPException(status_code=400, detail="Primary link must be connected to this device")


@router.get("", response_model=List[DeviceRead])
async def list_devices(
    status: Optional[DeviceStatus] = None,
    location: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Device)
    if status:
        query = query.where(Device.status == status)
    if location:
        query = query.where(Device.location.ilike(f"%{location}%"))
    result = await db.execute(query.order_by(Device.name))
    return result.scalars().all()


from app.services.icmp_monitor import ping_target

@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(device_in: DeviceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Device).where(Device.name == device_in.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Device with this name already exists")

    await _validate_device_dependencies(
        db,
        None,
        device_in.gateway_device_id,
        device_in.primary_link_id,
    )

    device = Device(**device_in.model_dump())

    # Immediate probe on registration
    if device.ip_address:
        ping_res = await ping_target(device.ip_address, count=2)
        if ping_res["is_up"]:
            device.status = DeviceStatus.ONLINE
        else:
            device.status = DeviceStatus.OFFLINE

    db.add(device)
    await db.flush()

    # A selected gateway represents the upstream topology dependency. Create
    # its primary link in the same transaction so no orphan device is exposed.
    if device.gateway_device_id is not None:
        gateway = await db.get(Device, device.gateway_device_id)
        if not device.gateway_ip_address and gateway.ip_address:
            device.gateway_ip_address = gateway.ip_address
        link = await _create_auto_gateway_link(db, device, gateway)
        device.primary_link_id = link.id

    await db.commit()
    await db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/{device_id}/windows-monitoring", response_model=WindowsConnectionRead | None)
async def get_windows_monitoring(device_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(Device, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device_id,
        DeviceMonitoringCredential.provider == "WINDOWS"))).scalar_one_or_none()
    if not credential: return None
    return WindowsConnectionRead.model_validate(credential)


@router.put("/{device_id}/windows-monitoring", response_model=WindowsConnectionRead)
async def configure_windows_monitoring(device_id: int, data: WindowsConnectionInput,
                                       db: AsyncSession = Depends(get_db)):
    if not await db.get(Device, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device_id,
        DeviceMonitoringCredential.provider == "WINDOWS"))).scalar_one_or_none()
    if not credential:
        if not data.password:
            raise HTTPException(status_code=400, detail="Password is required for the first configuration")
        credential = DeviceMonitoringCredential(device_id=device_id, provider="WINDOWS",
            username=data.username, encrypted_password=encrypt_secret(data.password))
        db.add(credential)
    credential.username = data.username
    credential.port = data.port
    credential.use_https = data.use_https
    credential.verify_certificate = data.verify_certificate
    credential.authentication = data.authentication
    credential.enabled = data.enabled
    if data.password: credential.encrypted_password = encrypt_secret(data.password)
    for other in (await db.execute(select(DeviceMonitoringCredential).where(
            DeviceMonitoringCredential.device_id == device_id,
            DeviceMonitoringCredential.provider != "WINDOWS"))).scalars().all():
        other.enabled = False
    await db.commit(); await db.refresh(credential)
    return WindowsConnectionRead.model_validate(credential)


@router.post("/{device_id}/windows-monitoring/test", response_model=WindowsCapabilityRead)
async def test_windows_monitoring(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(status_code=404, detail="Device not found")
    if not device.ip_address: raise HTTPException(status_code=400, detail="Device has no IP address")
    _reject_loopback_windows_target(device)
    if device.status != DeviceStatus.ONLINE:
        raise HTTPException(status_code=409, detail="Device must be online before Windows monitoring is tested")
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device_id,
        DeviceMonitoringCredential.provider == "WINDOWS",
        DeviceMonitoringCredential.enabled.is_(True)))).scalar_one_or_none()
    if not credential: raise HTTPException(status_code=400, detail="Configure Windows monitoring first")
    capability = (await db.execute(select(DeviceCapability).where(
        DeviceCapability.device_id == device_id,
        DeviceCapability.provider == "WINDOWS"))).scalar_one_or_none()
    if not capability:
        capability = DeviceCapability(device_id=device_id, provider="WINDOWS", platform="windows")
        db.add(capability)
    password = decrypt_secret(credential.encrypted_password)
    if password is None: raise HTTPException(status_code=409, detail="Stored monitoring credentials cannot be decrypted")
    provider = WindowsMonitoringProvider(WinRMTransport(device.ip_address, credential.username, password,
        credential.port, credential.use_https, credential.verify_certificate, credential.authentication))
    now = datetime.now(timezone.utc)
    try:
        detected = await provider.detect_capabilities()
        capability.provider_mode = detected.provider_mode
        capability.operating_system = detected.operating_system
        capability.powershell_version = detected.powershell_version
        capability.capabilities = detected.capabilities
        capability.diagnostics = detected.diagnostics
        capability.last_status = "READY"
        capability.last_error_code = None
        capability.discovered_at = now
        await db.commit()
        return WindowsCapabilityRead(device_id=device.id, device_name=device.name,
            connectivity=True, winrm=True, authentication=True, service_discovery=True,
            status="READY", message="Ready for Discovery", operating_system=detected.operating_system,
            powershell_version=detected.powershell_version, provider_mode=detected.provider_mode,
            capabilities=detected.capabilities, diagnostics=detected.diagnostics, discovered_at=now)
    except WindowsMonitoringError as exc:
        capability.last_status = "FAILED"; capability.last_error_code = exc.code; capability.discovered_at = now
        await db.commit()
        return WindowsCapabilityRead(device_id=device.id, device_name=device.name,
            connectivity=exc.code not in {"WINRM_UNAVAILABLE", "CHECK_TIMEOUT"}, winrm=False,
            authentication=exc.code not in {"AUTHENTICATION_FAILED", "WINRM_UNAVAILABLE", "CHECK_TIMEOUT"},
            service_discovery=False, status="FAILED", error_code=exc.code, message=str(exc), discovered_at=now)


@router.post("/{device_id}/windows-monitoring/test-candidate", response_model=WindowsCapabilityRead)
async def test_windows_monitoring_candidate(device_id: int, data: WindowsConnectionInput,
                                            db: AsyncSession = Depends(get_db)):
    """Test supplied settings without persisting credentials or connection configuration."""
    device = await db.get(Device, device_id)
    if not device: raise HTTPException(status_code=404, detail="Device not found")
    if not device.ip_address: raise HTTPException(status_code=400, detail="Device has no IP address")
    _reject_loopback_windows_target(device)
    if device.status != DeviceStatus.ONLINE:
        raise HTTPException(status_code=409, detail="Device must be online before remote monitoring is tested")
    password = data.password
    if not password:
        stored = (await db.execute(select(DeviceMonitoringCredential).where(
            DeviceMonitoringCredential.device_id == device_id,
            DeviceMonitoringCredential.provider == "WINDOWS"))).scalar_one_or_none()
        password = decrypt_secret(stored.encrypted_password) if stored else None
    if not password: raise HTTPException(status_code=400, detail="Password is required to test this connection")
    provider = WindowsMonitoringProvider(WinRMTransport(device.ip_address, data.username, password,
        data.port, data.use_https, data.verify_certificate, data.authentication))
    now = datetime.now(timezone.utc)
    try:
        detected = await provider.detect_capabilities()
        return WindowsCapabilityRead(device_id=device.id, device_name=device.name, connectivity=True,
            winrm=True, authentication=True, service_discovery=True, status="READY",
            message="Connection verified. You can now save and continue.",
            operating_system=detected.operating_system, powershell_version=detected.powershell_version,
            provider_mode=detected.provider_mode, capabilities=detected.capabilities,
            diagnostics=detected.diagnostics, discovered_at=now)
    except WindowsMonitoringError as exc:
        return WindowsCapabilityRead(device_id=device.id, device_name=device.name,
            connectivity=exc.code not in {"WINRM_UNAVAILABLE", "CHECK_TIMEOUT"}, winrm=False,
            authentication=exc.code not in {"AUTHENTICATION_FAILED", "WINRM_UNAVAILABLE", "CHECK_TIMEOUT"},
            service_discovery=False, status="FAILED", error_code=exc.code, message=str(exc), discovered_at=now)


@router.get("/{device_id}/linux-monitoring", response_model=LinuxConnectionRead | None)
async def get_linux_monitoring(device_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(Device, device_id): raise HTTPException(404, "Device not found")
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device_id,
        DeviceMonitoringCredential.provider == "LINUX"))).scalar_one_or_none()
    if not credential: return None
    capability = (await db.execute(select(DeviceCapability).where(
        DeviceCapability.device_id == device_id, DeviceCapability.provider == "LINUX"))).scalar_one_or_none()
    return LinuxConnectionRead(username=credential.username, port=credential.port,
        authentication=credential.authentication, verify_host_key=credential.verify_certificate,
        enabled=credential.enabled, secret_configured=bool(credential.encrypted_password),
        host_key=(capability.diagnostics or {}).get("host_key") if capability else None)


@router.put("/{device_id}/linux-monitoring", response_model=LinuxConnectionRead)
async def configure_linux_monitoring(device_id: int, data: LinuxConnectionInput,
                                     db: AsyncSession = Depends(get_db)):
    if not await db.get(Device, device_id): raise HTTPException(404, "Device not found")
    if data.verify_host_key and not data.host_key:
        raise HTTPException(400, "A verified SSH host key is required")
    credential = (await db.execute(select(DeviceMonitoringCredential).where(
        DeviceMonitoringCredential.device_id == device_id,
        DeviceMonitoringCredential.provider == "LINUX"))).scalar_one_or_none()
    if not credential:
        if not data.secret: raise HTTPException(400, "Password or private key is required for the first configuration")
        credential = DeviceMonitoringCredential(device_id=device_id, provider="LINUX", username=data.username,
            encrypted_password=encrypt_secret(data.secret)); db.add(credential)
    credential.username=data.username; credential.port=data.port; credential.use_https=False
    credential.verify_certificate=data.verify_host_key; credential.authentication=data.authentication
    credential.enabled=data.enabled
    if data.secret: credential.encrypted_password=encrypt_secret(data.secret)
    capability = (await db.execute(select(DeviceCapability).where(
        DeviceCapability.device_id == device_id, DeviceCapability.provider == "LINUX"))).scalar_one_or_none()
    if not capability:
        capability=DeviceCapability(device_id=device_id,provider="LINUX",platform="linux"); db.add(capability)
    capability.diagnostics={**(capability.diagnostics or {}),"host_key":data.host_key}
    capability.last_status="READY"; capability.discovered_at=datetime.now(timezone.utc)
    for other in (await db.execute(select(DeviceMonitoringCredential).where(
            DeviceMonitoringCredential.device_id == device_id,
            DeviceMonitoringCredential.provider != "LINUX"))).scalars().all():
        other.enabled=False
    await db.commit(); await db.refresh(credential)
    return LinuxConnectionRead(username=credential.username,port=credential.port,
        authentication=credential.authentication,verify_host_key=credential.verify_certificate,
        enabled=credential.enabled,secret_configured=True,host_key=data.host_key)


@router.post("/{device_id}/linux-monitoring/test-candidate")
async def test_linux_monitoring_candidate(device_id: int, data: LinuxConnectionInput,
                                          db: AsyncSession = Depends(get_db)):
    device=await db.get(Device,device_id)
    if not device: raise HTTPException(404,"Device not found")
    if not device.ip_address: raise HTTPException(400,"Device has no IP address")
    if device.status != DeviceStatus.ONLINE: raise HTTPException(409,"Device must be online before remote monitoring is tested")
    secret=data.secret
    if not secret:
        stored=(await db.execute(select(DeviceMonitoringCredential).where(
            DeviceMonitoringCredential.device_id==device_id,
            DeviceMonitoringCredential.provider=="LINUX"))).scalar_one_or_none()
        secret=decrypt_secret(stored.encrypted_password) if stored else None
    if not secret: raise HTTPException(400,"Password or private key is required to test this connection")
    transport=SSHTransport(device.ip_address,data.username,secret,data.port,data.authentication,
        data.host_key,verify_host_key=bool(data.host_key) and data.verify_host_key)
    provider=LinuxMonitoringProvider(transport); now=datetime.now(timezone.utc)
    try:
        detected=await provider.detect_capabilities()
        return {"device_id":device.id,"device_name":device.name,"connectivity":True,"ssh":True,
            "authentication":True,"service_discovery":detected.capabilities.get("services",False),
            "status":"READY","message":"Connection verified. Confirm the host key, then save and continue.",
            "operating_system":detected.operating_system,"provider_mode":detected.provider_mode,
            "capabilities":detected.capabilities,"diagnostics":detected.diagnostics,"discovered_at":now}
    except LinuxMonitoringError as exc:
        return {"device_id":device.id,"device_name":device.name,
            "connectivity":exc.code not in {"SSH_UNAVAILABLE","CHECK_TIMEOUT"},"ssh":False,
            "authentication":exc.code not in {"AUTHENTICATION_FAILED","SSH_UNAVAILABLE","CHECK_TIMEOUT"},
            "service_discovery":False,"status":"FAILED","error_code":exc.code,"message":str(exc),
            "diagnostics":{"host_key":transport.observed_host_key},"discovered_at":now}


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(device_id: int, device_in: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = device_in.model_dump(exclude_unset=True)
    old_gateway_device_id = device.gateway_device_id
    gateway_changed = (
        "gateway_device_id" in update_data
        and update_data["gateway_device_id"] != old_gateway_device_id
    )
    await _validate_device_dependencies(
        db,
        device_id,
        update_data.get("gateway_device_id", device.gateway_device_id),
        update_data.get("primary_link_id", device.primary_link_id),
    )
    for field, value in update_data.items():
        setattr(device, field, value)

    auto_link = await _find_auto_gateway_link(db, device.id)
    if device.gateway_device_id is not None:
        gateway = await db.get(Device, device.gateway_device_id)
        if gateway_changed:
            device.gateway_ip_address = gateway.ip_address

        if auto_link is None:
            auto_link = await _create_auto_gateway_link(db, device, gateway)
        else:
            auto_link.source_device_id = gateway.id
            auto_link.destination_device_id = device.id
            auto_link.source_interface_id = None
            auto_link.name = _auto_gateway_link_name(gateway, device)
            auto_link.status = LinkStatus.UNKNOWN
            auto_link.is_critical = device.is_critical

        # Respect an explicitly selected manual primary link. Otherwise the
        # automatically managed gateway link remains the device primary link.
        selected_primary_link_id = update_data.get("primary_link_id")
        if selected_primary_link_id is None or selected_primary_link_id == auto_link.id:
            device.primary_link_id = auto_link.id
    elif gateway_changed and auto_link is not None:
        # Gateway was intentionally removed. Detach the managed link from the
        # device; it remains in Links so history is not silently destroyed.
        if device.primary_link_id == auto_link.id:
            device.primary_link_id = None
        auto_link.description = (
            "Enlace automático preservado após remoção do gateway; revise ou exclua manualmente."
        )
        auto_link.status = LinkStatus.UNKNOWN

    await db.commit()
    await db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    from sqlalchemy import delete, or_
    from app.models.link import Link
    from app.models.interface import Interface
    from app.models.redundancy_group import RedundancyGroup
    from app.models.monitoring_result import MonitoringResult
    from app.models.alert import Alert

    # Remove redundancy groups that directly pair this device with another one.
    device_rg_res = await db.execute(
        select(RedundancyGroup.id).where(
            or_(
                RedundancyGroup.primary_device_id == device_id,
                RedundancyGroup.secondary_device_id == device_id,
            )
        )
    )
    device_rg_ids = device_rg_res.scalars().all()
    if device_rg_ids:
        await db.execute(delete(Alert).where(Alert.redundancy_group_id.in_(device_rg_ids)))
        await db.execute(delete(RedundancyGroup).where(RedundancyGroup.id.in_(device_rg_ids)))

    # Find associated links
    links_res = await db.execute(
        select(Link.id).where(or_(Link.source_device_id == device_id, Link.destination_device_id == device_id))
    )
    link_ids = links_res.scalars().all()

    if link_ids:
        # Clear references before deleting the links to keep foreign-key checks valid.
        devices_with_primary_link = (
            await db.execute(select(Device).where(Device.primary_link_id.in_(link_ids)))
        ).scalars().all()
        for linked_device in devices_with_primary_link:
            linked_device.primary_link_id = None

        # Find redundancy group IDs
        rg_res = await db.execute(
            select(RedundancyGroup.id).where(
                or_(RedundancyGroup.primary_link_id.in_(link_ids), RedundancyGroup.secondary_link_id.in_(link_ids))
            )
        )
        rg_ids = rg_res.scalars().all()
        if rg_ids:
            await db.execute(delete(Alert).where(Alert.redundancy_group_id.in_(rg_ids)))
            await db.execute(delete(RedundancyGroup).where(RedundancyGroup.id.in_(rg_ids)))

        await db.execute(delete(Alert).where(Alert.link_id.in_(link_ids)))
        await db.execute(
            delete(MonitoringResult).where(
                MonitoringResult.target_type == "LINK", MonitoringResult.target_id.in_(link_ids)
            )
        )
        await db.execute(delete(Link).where(Link.id.in_(link_ids)))

    # Delete device alerts, interfaces, monitoring results
    await db.execute(delete(Alert).where(Alert.device_id == device_id))
    await db.execute(delete(Interface).where(Interface.device_id == device_id))
    await db.execute(
        delete(MonitoringResult).where(
            MonitoringResult.target_type == "DEVICE", MonitoringResult.target_id == device_id
        )
    )
    dependents = (
        await db.execute(select(Device).where(Device.gateway_device_id == device_id))
    ).scalars().all()
    for dependent in dependents:
        dependent.gateway_device_id = None

    await db.delete(device)
    await db.commit()


@router.get("/{device_id}/status", response_model=DeviceStatusRead)
async def get_device_status(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.ip_address:
        return DeviceStatusRead(
            id=device.id,
            name=device.name,
            status=DeviceStatus.UNKNOWN,
            ip_address=device.ip_address,
            gateway_ip_address=device.gateway_ip_address,
            gateway_device_id=device.gateway_device_id,
            primary_link_id=device.primary_link_id,
            last_latency_ms=None,
            last_packet_loss_pct=None,
            updated_at=device.updated_at,
        )

    ping_res = await ping_target(device.ip_address, count=2)
    return DeviceStatusRead(
        id=device.id,
        name=device.name,
        status=DeviceStatus.ONLINE if ping_res["is_up"] else DeviceStatus.OFFLINE,
        ip_address=device.ip_address,
        gateway_ip_address=device.gateway_ip_address,
        gateway_device_id=device.gateway_device_id,
        primary_link_id=device.primary_link_id,
        last_latency_ms=ping_res.get("latency_ms"),
        last_packet_loss_pct=ping_res.get("packet_loss_pct"),
        updated_at=device.updated_at,
    )
