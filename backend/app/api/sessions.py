import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Session as DBSession, GazeTelemetryBatch
from app.schemas import SessionOut, TelemetryBatchIn

router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(DBSession).where(DBSession.id == session_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Session not found")
    return row


@router.put("/sessions/{session_id}/end", status_code=200)
async def end_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(DBSession).where(DBSession.id == session_id))).scalar_one_or_none()
    if row and row.ended_at is None:
        row.ended_at = datetime.now(timezone.utc)
        await db.commit()
    return {"status": "ok"}


@router.post("/telemetry/batch", status_code=201)
async def save_telemetry_batch(body: TelemetryBatchIn, db: AsyncSession = Depends(get_db)):
    """Manual batch endpoint — used when the caller manages its own flush cycle."""
    batch = GazeTelemetryBatch(
        session_id=body.session_id,
        payload=[p.model_dump() for p in body.points],
    )
    db.add(batch)
    await db.commit()
    return {"status": "ok", "saved": len(body.points)}


@router.get("/sessions/{session_id}/telemetry")
async def get_session_telemetry(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return all gaze batches for a session — useful for replay / export."""
    rows = (
        await db.execute(
            select(GazeTelemetryBatch)
            .where(GazeTelemetryBatch.session_id == session_id)
            .order_by(GazeTelemetryBatch.created_at)
        )
    ).scalars().all()
    return [{"id": str(r.id), "created_at": r.created_at, "points": r.payload} for r in rows]
