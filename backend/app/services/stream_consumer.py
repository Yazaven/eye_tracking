import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.redis import get_redis, STREAM_KEY
from app.services.gaze_tracker import GazeTracker

_thread_local = threading.local()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mediapipe")

_last_drop_log = 0.0


def _process_in_thread(frame_bytes: bytes) -> tuple[float, float] | None:
    if not hasattr(_thread_local, "tracker"):
        _thread_local.tracker = GazeTracker()
    return _thread_local.tracker.process(frame_bytes)


async def run_consumer() -> None:
    global _last_drop_log

    r = await get_redis()
    loop = asyncio.get_running_loop()
    last_id: bytes | str = "$"

    print(f"[Consumer] Listening on stream '{STREAM_KEY}'")

    while True:
        try:
            # Read up to 500 pending messages in one shot
            entries = await r.xread({STREAM_KEY: last_id}, block=100, count=500)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[Consumer] Redis read error: {exc} — retrying in 2 s")
            await asyncio.sleep(2)
            continue

        if not entries:
            continue

        _, messages = entries[0]
        if not messages:
            continue

        # Advance past every message in this batch so stale frames are never re-read
        last_id = messages[-1][0]

        # Keep only the most-recent frame per session; drop everything older
        latest: dict[str, bytes] = {}
        for _, fields in messages:
            try:
                sid = fields[b"session_id"].decode()
                latest[sid] = fields[b"frame"]
            except (KeyError, UnicodeDecodeError):
                continue

        dropped = len(messages) - len(latest)
        if dropped > 0:
            now = time.monotonic()
            if now - _last_drop_log >= 5.0:
                print(f"[Consumer] Dropped {dropped} stale frame(s) — processing at capacity")
                _last_drop_log = now

        for session_id, frame_bytes in latest.items():
            try:
                result = await loop.run_in_executor(
                    _executor, _process_in_thread, frame_bytes
                )
            except Exception as exc:
                print(f"[Consumer] MediaPipe error for session {session_id[:8]}: {exc}")
                continue

            if result is not None:
                x, y = result
                payload = json.dumps({
                    "type": "gaze",
                    "ts": time.time(),
                    "x": round(x, 4),
                    "y": round(y, 4),
                })
                try:
                    await r.publish(f"gaze:results:{session_id}", payload)
                except Exception as exc:
                    print(f"[Consumer] Redis publish error: {exc}")
