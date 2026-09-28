from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.device import DeviceStatus, DeviceType
from app.models.link import LinkType
from app.schemas.link import LinkRead


class DeviceBase(BaseModel):
    name: str = Field(..., max_length=128)
    ip_address: Optional[str] = None
    gateway_ip_address: Optional[str] = None
    gateway_device_id: Optional[int] = None
    primary_link_id: Optional[int] = None
    device_type: DeviceType
    location: str = Field(..., max_length=128)
    network: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    function: Optional[str] = None
    group_name: Optional[str] = None
    icon_id: Optional[int] = None
    monitoring_method: str = "ICMP"
    snmp_community: Optional[str] = None
    snmp_port: int = 161
    is_critical: bool = False
    monitoring_interval: int = Field(default=30, ge=1)


class DeviceCreate(DeviceBase):
    pass


class DeviceRedundantCreate(BaseModel):
    """Atomically register a device and its two upstream redundancy links."""

    device: DeviceCreate
    redundancy_group_id: int
    link_type: LinkType = LinkType.OTHER
    link_monitoring_interval: int = Field(default=5, ge=1)
    links_are_critical: bool = True


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    gateway_ip_address: Optional[str] = None
    gateway_device_id: Optional[int] = None
    primary_link_id: Optional[int] = None
    device_type: Optional[DeviceType] = None
    location: Optional[str] = None
    network: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    function: Optional[str] = None
    group_name: Optional[str] = None
    icon_id: Optional[int] = None
    monitoring_method: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = None
    is_critical: Optional[bool] = None
    monitoring_interval: Optional[int] = None


class DeviceRead(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: DeviceStatus
    created_at: datetime
    updated_at: datetime
    snmp_community: Optional[str] = Field(default=None, exclude=True)
    snmp_configured: bool = False


class DeviceRedundantRead(BaseModel):
    device: DeviceRead
    primary_link: LinkRead
    secondary_link: LinkRead


class DeviceStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: DeviceStatus
    ip_address: Optional[str]
    gateway_ip_address: Optional[str] = None
    gateway_device_id: Optional[int] = None
    primary_link_id: Optional[int] = None
    last_latency_ms: Optional[float] = None
    last_packet_loss_pct: Optional[float] = None
    updated_at: datetime
