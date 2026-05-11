# Real-Time Gaze Heatmap

Streams webcam frames over a binary WebSocket to a FastAPI backend, runs MediaPipe iris tracking on each frame, and overlays a live heatmap on the page showing where the user is looking.

## Stack

Next.js 14, TypeScript, FastAPI, Python 3.12, MediaPipe FaceMesh, Redis Streams, PostgreSQL, Docker Compose

## How it works

The browser captures the webcam at 30 fps using `canvas.toBlob()` and sends raw binary frames over WebSocket — no base64 encoding. The backend pushes each frame into a Redis Stream. A background consumer reads the stream and runs MediaPipe in a thread pool (one `FaceMesh` instance per thread since it's not reentrant), then publishes the gaze result to a per-session Redis Pub/Sub channel. The WebSocket handler picks that up and forwards it to the browser as `{x, y}` coordinates. A Canvas overlay draws a radial gradient at those coordinates and decays old blobs each frame using `destination-out` compositing.

Sessions and gaze points are persisted to PostgreSQL on disconnect.

## Gaze accuracy (no calibration)

Three techniques are applied to improve raw MediaPipe output without requiring a calibration step:

- **Eye-relative normalisation** — iris position is expressed as a fraction of each eye's bounding box, which removes head-distance and head-position bias.
- **Blink filtering** — Eye Aspect Ratio below 0.15 skips the frame so blinks don't leave artefacts on the heatmap.
- **Kalman filter** — 4-state (x, y, vx, vy) smoother that reduces landmark jitter without perceptible lag at 30 fps.

## Run

```bash
docker compose up
```

Frontend at `http://localhost:3000`, API docs at `http://localhost:8000/docs`.

## API

- `GET /health`
- `WS /ws/gaze/{session_id}?w=&h=` — frame ingestion and gaze stream
- `GET /api/v1/sessions/{id}`
- `GET /api/v1/sessions/{id}/telemetry`
- `PUT /api/v1/sessions/{id}/end`
- `POST /api/v1/telemetry/batch`
