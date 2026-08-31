from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from app.models.alert import AlertSeverity


class AlertBase(BaseModel):
    severity: AlertSeverity
    title: str
    message: str
    device_id: Optional[int] = None
    link_id: Optional[int] = None
    redundancy_group_id: Optional[int] = None
    root_cause: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class AlertRead(AlertBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_resolved: bool
    notified_channels: Optional[List[str]] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
