import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    id: uuid.UUID
    screen_width: int
    screen_height: int
    created_at: datetime
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}


class GazePoint(BaseModel):
    ts: float
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class TelemetryBatchIn(BaseModel):
    session_id: uuid.UUID
    points: list[GazePoint] = Field(min_length=1)
