from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.link import LinkPriority, LinkStatus, LinkType


class LinkBase(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    source_device_id: int
    destination_device_id: int
    source_interface_id: Optional[int] = None
    destination_interface_id: Optional[int] = None
    link_type: LinkType
    priority: LinkPriority
    is_critical: bool = False
    monitoring_interval: int = Field(default=5, ge=1)


class LinkCreate(LinkBase):
    pass


class LinkUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    source_device_id: Optional[int] = None
    destination_device_id: Optional[int] = None
    source_interface_id: Optional[int] = None
    destination_interface_id: Optional[int] = None
    link_type: Optional[LinkType] = None
    priority: Optional[LinkPriority] = None
    is_critical: Optional[bool] = None
    monitoring_interval: Optional[int] = None


class LinkRead(LinkBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: LinkStatus
    created_at: datetime
    updated_at: datetime
