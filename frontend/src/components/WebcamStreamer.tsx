'use client';

import { useEffect, useRef } from 'react';
import { useGazeStore } from '@/lib/store';
import { getGazeSocket, destroyGazeSocket } from '@/lib/websocket';

const CAPTURE_W = 320;
const CAPTURE_H = 240;
// 15 fps matches realistic CPU-only MediaPipe throughput.
// Sending faster than the backend can process just builds a lag queue.
const TARGET_FPS = 15;
const FRAME_INTERVAL_MS = 1000 / TARGET_FPS;
const JPEG_QUALITY = 0.5;

interface Props {
  sessionId: string;
}

export default function WebcamStreamer({ sessionId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const lastFrameTs = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);

  const { setIsTracking, setConnectionStatus, setCameraError, setGazePoint, setLastGazeTs } =
    useGazeStore();

  useEffect(() => {
    const ws = getGazeSocket(sessionId);

    ws.connect(
      (gaze) => {
        setGazePoint({ x: gaze.x, y: gaze.y });
        setLastGazeTs(performance.now());
      },
      (status) => setConnectionStatus(status),
    );

    async function startCamera(): Promise<void> {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: 'user',
            frameRate: { ideal: TARGET_FPS },
          },
          audio: false,
        });

        streamRef.current = stream;
        const video = videoRef.current!;
        video.srcObject = stream;
        await video.play();

        setIsTracking(true);
        setCameraError(null);

        const ctx = canvasRef.current!.getContext('2d', { willReadFrequently: false })!;

        const loop = (): void => {
          rafRef.current = requestAnimationFrame(loop);

          const now = performance.now();
          if (now - lastFrameTs.current < FRAME_INTERVAL_MS) return;
          lastFrameTs.current = now;

          if (video.readyState < video.HAVE_CURRENT_DATA) return;

          ctx.drawImage(video, 0, 0, CAPTURE_W, CAPTURE_H);

          canvasRef.current!.toBlob(
            (blob) => { if (blob) ws.sendFrame(blob); },
            'image/jpeg',
            JPEG_QUALITY,
          );
        };

        rafRef.current = requestAnimationFrame(loop);
      } catch (err) {
        const msg =
          err instanceof DOMException &&
          (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')
            ? 'Camera access was denied. Allow camera permissions and refresh.'
            : err instanceof DOMException && err.name === 'NotFoundError'
              ? 'No camera found. Connect a webcam and refresh.'
              : err instanceof DOMException && err.name === 'NotReadableError'
                ? 'Camera is in use by another application.'
                : `Camera error: ${err instanceof Error ? err.message : String(err)}`;

        setCameraError(msg);
        setIsTracking(false);
      }
    }

    startCamera();

    return () => {
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      destroyGazeSocket();
      setIsTracking(false);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return (
    <>
      <video ref={videoRef} className="hidden" muted playsInline />
      <canvas ref={canvasRef} width={CAPTURE_W} height={CAPTURE_H} className="hidden" />
    </>
  );
}
