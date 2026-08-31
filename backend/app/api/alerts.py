from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert, AlertSeverity
from app.schemas.alert import AlertRead

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("", response_model=List[AlertRead])
async def list_alerts(
    severity: Optional[AlertSeverity] = None,
    is_resolved: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert)
    if severity:
        query = query.where(Alert.severity == severity)
    if is_resolved is not None:
        query = query.where(Alert.is_resolved == is_resolved)
    
    result = await db.execute(query.order_by(Alert.created_at.desc()).limit(limit))
    return result.scalars().all()


@router.put("/{alert_id}/resolve", response_model=AlertRead)
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if not alert.is_resolved:
        alert.is_resolved = True
        alert.resolved_at = datetime.utcnow()
        await db.commit()
        await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_alerts(db: AsyncSession = Depends(get_db)):
    alerts = (await db.execute(select(Alert))).scalars().all()
    for a in alerts:
        await db.delete(a)
    await db.commit()
