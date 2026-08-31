from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.redundancy_group import RedundancyStatus, RedundancyType, ServiceCheckType
from app.schemas.device import DeviceRead
from app.schemas.link import LinkRead


class RedundancyGroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    redundancy_type: RedundancyType = RedundancyType.LINK
    primary_link_id: Optional[int] = None
    secondary_link_id: Optional[int] = None
    primary_device_id: Optional[int] = None
    secondary_device_id: Optional[int] = None
    service_check_type: ServiceCheckType = ServiceCheckType.NONE
    service_check_target: Optional[str] = None
    service_check_port: Optional[int] = None


class RedundancyGroupCreate(RedundancyGroupBase):
    pass


class RedundancyGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    redundancy_type: Optional[RedundancyType] = None
    primary_link_id: Optional[int] = None
    secondary_link_id: Optional[int] = None
    primary_device_id: Optional[int] = None
    secondary_device_id: Optional[int] = None
    service_check_type: Optional[ServiceCheckType] = None
    service_check_target: Optional[str] = None
    service_check_port: Optional[int] = None


class RedundancyGroupRead(RedundancyGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RedundancyStatus
    last_evaluated: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class RedundancyGroupDetail(RedundancyGroupRead):
    primary_link: Optional[LinkRead] = None
    secondary_link: Optional[LinkRead] = None
    primary_device: Optional[DeviceRead] = None
    secondary_device: Optional[DeviceRead] = None
