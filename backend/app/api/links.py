from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.models.interface import Interface
from app.models.link import Link, LinkStatus
from app.schemas.link import LinkCreate, LinkRead, LinkUpdate

router = APIRouter(prefix="/api/links", tags=["Links"])


async def _validate_link_payload(
    db: AsyncSession,
    source_device_id: int,
    destination_device_id: int,
    source_interface_id: int | None,
    destination_interface_id: int | None,
) -> None:
    if source_device_id == destination_device_id:
        raise HTTPException(status_code=400, detail="Source and destination devices must be different")

    source_device = await db.get(Device, source_device_id)
    destination_device = await db.get(Device, destination_device_id)
    if not source_device:
        raise HTTPException(status_code=400, detail="Source device not found")
    if not destination_device:
        raise HTTPException(status_code=400, detail="Destination device not found")

    if source_interface_id is not None:
        source_interface = await db.get(Interface, source_interface_id)
        if not source_interface or source_interface.device_id != source_device_id:
            raise HTTPException(status_code=400, detail="Source interface does not belong to source device")

    if destination_interface_id is not None:
        destination_interface = await db.get(Interface, destination_interface_id)
        if not destination_interface or destination_interface.device_id != destination_device_id:
            raise HTTPException(status_code=400, detail="Destination interface does not belong to destination device")


@router.get("", response_model=List[LinkRead])
async def list_links(
    status: Optional[LinkStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Link)
    if status:
        query = query.where(Link.status == status)
    result = await db.execute(query.order_by(Link.name))
    return result.scalars().all()


@router.post("", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
async def create_link(link_in: LinkCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Link).where(Link.name == link_in.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Link with this name already exists")

    await _validate_link_payload(
        db,
        link_in.source_device_id,
        link_in.destination_device_id,
        link_in.source_interface_id,
        link_in.destination_interface_id,
    )

    link = Link(**link_in.model_dump())
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


@router.get("/{link_id}", response_model=LinkRead)
async def get_link(link_id: int, db: AsyncSession = Depends(get_db)):
    link = await db.get(Link, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return link


@router.put("/{link_id}", response_model=LinkRead)
async def update_link(link_id: int, link_in: LinkUpdate, db: AsyncSession = Depends(get_db)):
    link = await db.get(Link, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    update_data = link_in.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != link.name:
        existing = await db.execute(select(Link).where(Link.name == update_data["name"]))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Link with this name already exists")

    await _validate_link_payload(
        db,
        update_data.get("source_device_id", link.source_device_id),
        update_data.get("destination_device_id", link.destination_device_id),
        update_data.get("source_interface_id", link.source_interface_id),
        update_data.get("destination_interface_id", link.destination_interface_id),
    )
    for field, value in update_data.items():
        setattr(link, field, value)

    await db.commit()
    await db.refresh(link)
    return link


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: int, db: AsyncSession = Depends(get_db)):
    link = await db.get(Link, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    from sqlalchemy import delete, or_
    from app.models.redundancy_group import RedundancyGroup
    from app.models.monitoring_result import MonitoringResult
    from app.models.alert import Alert

    # Find redundancy group IDs
    rg_res = await db.execute(
        select(RedundancyGroup.id).where(
            or_(RedundancyGroup.primary_link_id == link_id, RedundancyGroup.secondary_link_id == link_id)
        )
    )
    rg_ids = rg_res.scalars().all()
    if rg_ids:
        await db.execute(delete(Alert).where(Alert.redundancy_group_id.in_(rg_ids)))
        await db.execute(delete(RedundancyGroup).where(RedundancyGroup.id.in_(rg_ids)))

    await db.execute(delete(Alert).where(Alert.link_id == link_id))
    await db.execute(
        delete(MonitoringResult).where(
            MonitoringResult.target_type == "LINK", MonitoringResult.target_id == link_id
        )
    )
    devices = (
        await db.execute(select(Device).where(Device.primary_link_id == link_id))
    ).scalars().all()
    for device in devices:
        device.primary_link_id = None

    await db.delete(link)
    await db.commit()
