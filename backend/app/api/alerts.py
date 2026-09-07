from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert, AlertSeverity
from app.schemas.alert import AlertRead

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("", response_model=List[AlertRead])
async def list_alerts(
    response: Response,
    severity: Optional[AlertSeverity] = None,
    is_resolved: Optional[bool] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    source_type: Optional[str] = Query(default=None, pattern="^(DEVICE|LINK|REDUNDANCY_GROUP)$"),
    source_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=100, le=500),
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert)
    if severity:
        query = query.where(Alert.severity == severity)
    if is_resolved is not None:
        query = query.where(Alert.is_resolved == is_resolved)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Alert.title.ilike(term), Alert.message.ilike(term), Alert.root_cause.ilike(term)))
    source_columns = {"DEVICE": Alert.device_id, "LINK": Alert.link_id, "REDUNDANCY_GROUP": Alert.redundancy_group_id}
    if source_type:
        column = source_columns[source_type]
        query = query.where(column.is_not(None))
        if source_id is not None: query = query.where(column == source_id)
    elif source_id is not None:
        query = query.where(or_(Alert.device_id == source_id, Alert.link_id == source_id, Alert.redundancy_group_id == source_id))
    if start: query = query.where(Alert.created_at >= start)
    if end: query = query.where(Alert.created_at <= end)
    
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    result = await db.execute(query.order_by(Alert.created_at.desc()).offset((page-1)*limit).limit(limit))
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
