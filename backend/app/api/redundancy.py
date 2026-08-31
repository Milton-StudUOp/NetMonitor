from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.models.link import Link
from app.models.redundancy_group import RedundancyGroup, RedundancyStatus, RedundancyType
from app.schemas.redundancy import (
    RedundancyGroupCreate,
    RedundancyGroupDetail,
    RedundancyGroupRead,
    RedundancyGroupUpdate,
)

router = APIRouter(prefix="/api/redundancy-groups", tags=["Redundancy Groups"])


async def _validate_group_targets(db: AsyncSession, data: dict) -> None:
    redundancy_type = data.get("redundancy_type", RedundancyType.LINK)
    if redundancy_type == RedundancyType.LINK:
        primary_id = data.get("primary_link_id")
        secondary_id = data.get("secondary_link_id")
        if primary_id is None or secondary_id is None:
            raise HTTPException(status_code=400, detail="Select both primary and secondary links")
        if primary_id == secondary_id:
            raise HTTPException(status_code=400, detail="Primary and secondary links must be different")
        if not await db.get(Link, primary_id):
            raise HTTPException(status_code=400, detail="Primary link not found")
        if not await db.get(Link, secondary_id):
            raise HTTPException(status_code=400, detail="Secondary link not found")
    else:
        primary_id = data.get("primary_device_id")
        secondary_id = data.get("secondary_device_id")
        if primary_id is None or secondary_id is None:
            raise HTTPException(status_code=400, detail="Select both primary and secondary devices")
        if primary_id == secondary_id:
            raise HTTPException(status_code=400, detail="Primary and secondary devices must be different")
        if not await db.get(Device, primary_id):
            raise HTTPException(status_code=400, detail="Primary device not found")
        if not await db.get(Device, secondary_id):
            raise HTTPException(status_code=400, detail="Secondary device not found")


def _normalize_group_targets(data: dict) -> dict:
    if data.get("redundancy_type", RedundancyType.LINK) == RedundancyType.LINK:
        data["primary_device_id"] = None
        data["secondary_device_id"] = None
    else:
        data["primary_link_id"] = None
        data["secondary_link_id"] = None
    return data


@router.get("", response_model=List[RedundancyGroupDetail])
async def list_redundancy_groups(
    status: Optional[RedundancyStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(RedundancyGroup).options(
        selectinload(RedundancyGroup.primary_link),
        selectinload(RedundancyGroup.secondary_link),
        selectinload(RedundancyGroup.primary_device),
        selectinload(RedundancyGroup.secondary_device),
    )
    if status:
        query = query.where(RedundancyGroup.status == status)
    result = await db.execute(query.order_by(RedundancyGroup.name))
    return result.scalars().all()


@router.post("", response_model=RedundancyGroupRead, status_code=status.HTTP_201_CREATED)
async def create_redundancy_group(group_in: RedundancyGroupCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(RedundancyGroup).where(RedundancyGroup.name == group_in.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Redundancy group with this name already exists")

    group_data = _normalize_group_targets(group_in.model_dump())
    await _validate_group_targets(db, group_data)

    group = RedundancyGroup(**group_data)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.get("/{group_id}", response_model=RedundancyGroupDetail)
async def get_redundancy_group(group_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(RedundancyGroup)
        .where(RedundancyGroup.id == group_id)
        .options(
            selectinload(RedundancyGroup.primary_link),
            selectinload(RedundancyGroup.secondary_link),
            selectinload(RedundancyGroup.primary_device),
            selectinload(RedundancyGroup.secondary_device),
        )
    )
    result = await db.execute(query)
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Redundancy group not found")
    return group


@router.put("/{group_id}", response_model=RedundancyGroupRead)
async def update_redundancy_group(
    group_id: int, group_in: RedundancyGroupUpdate, db: AsyncSession = Depends(get_db)
):
    group = await db.get(RedundancyGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Redundancy group not found")

    update_data = group_in.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != group.name:
        existing = await db.execute(select(RedundancyGroup).where(RedundancyGroup.name == update_data["name"]))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Redundancy group with this name already exists")

    merged_data = {
        "redundancy_type": update_data.get("redundancy_type", group.redundancy_type),
        "primary_link_id": update_data.get("primary_link_id", group.primary_link_id),
        "secondary_link_id": update_data.get("secondary_link_id", group.secondary_link_id),
        "primary_device_id": update_data.get("primary_device_id", group.primary_device_id),
        "secondary_device_id": update_data.get("secondary_device_id", group.secondary_device_id),
    }
    merged_data = _normalize_group_targets(merged_data)
    await _validate_group_targets(db, merged_data)
    update_data.update(merged_data)
    for field, value in update_data.items():
        setattr(group, field, value)

    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_redundancy_group(group_id: int, db: AsyncSession = Depends(get_db)):
    group = await db.get(RedundancyGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Redundancy group not found")

    from sqlalchemy import delete
    from app.models.alert import Alert

    await db.execute(delete(Alert).where(Alert.redundancy_group_id == group_id))
    await db.delete(group)
    await db.commit()
