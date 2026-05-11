'use client';

import { useEffect, useRef } from 'react';
import { useGazeStore } from '@/lib/store';

const DECAY_RATE = 0.008;
const BLOB_RADIUS = 90;
const BLOB_ALPHA = 0.38;

export default function HeatmapOverlay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext('2d', { alpha: true })!;

    function resize(): void {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    let latestGaze = useGazeStore.getState().gazePoint;
    const unsub = useGazeStore.subscribe((s) => {
      latestGaze = s.gazePoint;
    });

    let rafId = 0;

    function render(): void {
      rafId = requestAnimationFrame(render);

      const w = canvas.width;
      const h = canvas.height;

      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = `rgba(0,0,0,${DECAY_RATE})`;
      ctx.fillRect(0, 0, w, h);

      ctx.globalCompositeOperation = 'source-over';

      if (!latestGaze) return;

      const px = latestGaze.x * w;
      const py = latestGaze.y * h;

      const grad = ctx.createRadialGradient(px, py, 0, px, py, BLOB_RADIUS);
      grad.addColorStop(0,    `rgba(255,   0,   0, ${BLOB_ALPHA})`);
      grad.addColorStop(0.30, `rgba(255, 120,   0, ${BLOB_ALPHA * 0.60})`);
      grad.addColorStop(0.60, `rgba(255, 230,   0, ${BLOB_ALPHA * 0.28})`);
      grad.addColorStop(0.85, `rgba(  0, 180, 255, ${BLOB_ALPHA * 0.08})`);
      grad.addColorStop(1,    'rgba(0,0,0,0)');

      ctx.fillStyle = grad;
      ctx.fillRect(px - BLOB_RADIUS, py - BLOB_RADIUS, BLOB_RADIUS * 2, BLOB_RADIUS * 2);
    }

    rafId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      unsub();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-40"
    />
  );
}
