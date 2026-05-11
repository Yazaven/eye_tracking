import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

from app.core.redis import get_redis, close_redis, STREAM_KEY
from app.core.database import init_db, close_db, AsyncSessionLocal
from app.models import Session as DBSession, GazeTelemetryBatch
from app.services.stream_consumer import run_consumer
from app.api.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    consumer_task = asyncio.create_task(run_consumer())
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        await close_redis()
        await close_db()


app = FastAPI(title="EyeTrek API", version="1.0.0", lifespan=lifespan)

app.include_router(sessions_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eyetrek-api"}


@app.websocket("/ws/gaze/{session_id}")
async def websocket_gaze(
    websocket: WebSocket,
    session_id: str,
    w: int = Query(default=1920),
    h: int = Query(default=1080),
):
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        await websocket.close(code=1008, reason="invalid session_id")
        return

    await websocket.accept()
    print(f"[WS] Connected  session={session_id}  screen={w}x{h}")

    try:
        async with AsyncSessionLocal() as db:
            db.add(DBSession(
                id=sid,
                screen_width=w,
                screen_height=h,
                user_agent=websocket.headers.get("user-agent"),
            ))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
    except Exception as exc:
        print(f"[WS] DB session create failed (non-fatal): {exc}")

    try:
        r = await get_redis()
    except Exception as exc:
        print(f"[WS] Redis unavailable: {exc}")
        await websocket.close(code=1011, reason="redis unavailable")
        return

    pubsub = r.pubsub()
    await pubsub.subscribe(f"gaze:results:{session_id}")

    frame_count = 0
    window_start = time.monotonic()
    gaze_buffer: list[dict] = []

    async def result_forwarder() -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    raw = message["data"].decode()
                    await websocket.send_text(raw)
                    data = json.loads(raw)
                    if data.get("type") == "gaze":
                        gaze_buffer.append({"ts": data["ts"], "x": data["x"], "y": data["y"]})
                except (WebSocketDisconnect, RuntimeError):
                    return
                except Exception as exc:
                    print(f"[WS] Forwarder send error: {exc}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[WS] Forwarder fatal error: {exc}")

    forwarder_task = asyncio.create_task(result_forwarder())

    try:
        while True:
            try:
                frame_bytes = await websocket.receive_bytes()
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                print(f"[WS] receive error: {exc}")
                break

            frame_count += 1

            now = time.monotonic()
            elapsed = now - window_start
            if elapsed >= 5.0:
                fps = frame_count / elapsed
                kb = len(frame_bytes) / 1024
                print(
                    f"[WS] session={session_id[:8]}  "
                    f"fps={fps:.1f}  last_frame={kb:.1f} KB  "
                    f"buffered_gaze={len(gaze_buffer)}"
                )
                frame_count = 0
                window_start = now

            try:
                await r.xadd(
                    STREAM_KEY,
                    {
                        b"session_id": session_id.encode(),
                        b"ts": str(time.time()).encode(),
                        b"frame": frame_bytes,
                    },
                    maxlen=60,
                    approximate=True,
                )
            except Exception as exc:
                print(f"[WS] Redis xadd error: {exc}")

    except WebSocketDisconnect:
        print(f"[WS] Disconnected  session={session_id}  gaze_points={len(gaze_buffer)}")
    finally:
        forwarder_task.cancel()
        try:
            await forwarder_task
        except asyncio.CancelledError:
            pass

        try:
            await pubsub.unsubscribe(f"gaze:results:{session_id}")
            await pubsub.aclose()
        except Exception:
            pass

        try:
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                row = (await db.execute(
                    select(DBSession).where(DBSession.id == sid)
                )).scalar_one_or_none()
                if row:
                    row.ended_at = datetime.now(timezone.utc)
                    if gaze_buffer:
                        db.add(GazeTelemetryBatch(session_id=sid, payload=gaze_buffer))
                    await db.commit()
                    print(f"[DB] Session {session_id[:8]} saved — {len(gaze_buffer)} gaze points")
        except Exception as exc:
            print(f"[WS] DB session save failed: {exc}")
