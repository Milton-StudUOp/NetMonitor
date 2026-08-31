from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.interface import InterfaceStatus


class InterfaceBase(BaseModel):
    device_id: int
    interface_name: str
    description: Optional[str] = None
    snmp_index: Optional[int] = None
    speed_mbps: Optional[int] = None


class InterfaceCreate(InterfaceBase):
    pass


class InterfaceUpdate(BaseModel):
    description: Optional[str] = None
    snmp_index: Optional[int] = None
    speed_mbps: Optional[int] = None
    status: Optional[InterfaceStatus] = None
    admin_status: Optional[InterfaceStatus] = None


class InterfaceRead(InterfaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: InterfaceStatus
    admin_status: InterfaceStatus
    bytes_in: int
    bytes_out: int
    errors_in: int
    errors_out: int
    discards_in: int
    discards_out: int
    last_change: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
