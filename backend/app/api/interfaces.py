from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.models.interface import Interface
from app.models.link import Link
from app.schemas.interface import InterfaceCreate, InterfaceRead, InterfaceUpdate

router = APIRouter(prefix="/api/interfaces", tags=["Interfaces"])


@router.get("", response_model=List[InterfaceRead])
async def list_interfaces(
    device_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Interface)
    if device_id:
        query = query.where(Interface.device_id == device_id)
    result = await db.execute(query.order_by(Interface.interface_name))
    return result.scalars().all()


@router.post("", response_model=InterfaceRead, status_code=status.HTTP_201_CREATED)
async def create_interface(interface_in: InterfaceCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Device, interface_in.device_id):
        raise HTTPException(status_code=400, detail="Device not found")

    existing = await db.execute(
        select(Interface).where(
            Interface.device_id == interface_in.device_id,
            Interface.interface_name == interface_in.interface_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Interface with this name already exists on this device")

    interface = Interface(**interface_in.model_dump())
    db.add(interface)
    await db.commit()
    await db.refresh(interface)
    return interface


@router.get("/{interface_id}", response_model=InterfaceRead)
async def get_interface(interface_id: int, db: AsyncSession = Depends(get_db)):
    interface = await db.get(Interface, interface_id)
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")
    return interface


@router.put("/{interface_id}", response_model=InterfaceRead)
async def update_interface(interface_id: int, interface_in: InterfaceUpdate, db: AsyncSession = Depends(get_db)):
    interface = await db.get(Interface, interface_id)
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")

    update_data = interface_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(interface, field, value)

    await db.commit()
    await db.refresh(interface)
    return interface


@router.delete("/{interface_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interface(interface_id: int, db: AsyncSession = Depends(get_db)):
    interface = await db.get(Interface, interface_id)
    if not interface:
        raise HTTPException(status_code=404, detail="Interface not found")

    links = (
        await db.execute(
            select(Link).where(
                (Link.source_interface_id == interface_id)
                | (Link.destination_interface_id == interface_id)
            )
        )
    ).scalars().all()
    for link in links:
        if link.source_interface_id == interface_id:
            link.source_interface_id = None
        if link.destination_interface_id == interface_id:
            link.destination_interface_id = None

    await db.delete(interface)
    await db.commit()
