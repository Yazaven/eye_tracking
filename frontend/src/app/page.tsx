'use client';

import { useState, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { useGazeStore } from '@/lib/store';
import type { ConnectionStatus } from '@/lib/websocket';

const WebcamStreamer = dynamic(() => import('@/components/WebcamStreamer'), { ssr: false });
const HeatmapOverlay = dynamic(() => import('@/components/HeatmapOverlay'), { ssr: false });

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  connected: 'text-green-400',
  connecting: 'text-yellow-400 animate-pulse',
  disconnected: 'text-gray-500',
  error: 'text-red-400',
};

const STATUS_DOT: Record<ConnectionStatus, string> = {
  connected: 'bg-green-400 animate-pulse',
  connecting: 'bg-yellow-400 animate-pulse',
  disconnected: 'bg-gray-600',
  error: 'bg-red-500',
};

export default function Home() {
  const [sessionId, setSessionId] = useState('');
  const [lagMs, setLagMs] = useState<number | null>(null);
  const lastGazeTsRef = useRef<number | null>(null);

  const { connectionStatus, isTracking, cameraError, gazePoint, lastGazeTs, setGazePoint } =
    useGazeStore();

  useEffect(() => {
    setSessionId(crypto.randomUUID());
  }, []);

  // Keep ref in sync so the interval always reads the latest timestamp without re-creating
  lastGazeTsRef.current = lastGazeTs;

  // Single stable interval — reads from ref, never recreated on gaze updates
  useEffect(() => {
    const id = setInterval(() => {
      const ts = lastGazeTsRef.current;
      setLagMs(ts === null ? null : Math.round(performance.now() - ts));
    }, 500);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Clear cursor when tracking stalls for more than 2 s
  useEffect(() => {
    if (lastGazeTs === null) return;
    const timer = setTimeout(() => setGazePoint(null), 2000);
    return () => clearTimeout(timer);
  }, [lastGazeTs, setGazePoint]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-gray-950 text-white">
      <h1 className="text-4xl font-bold tracking-tight">
        EyeTrek: Real-Time Gaze Heatmap
      </h1>

      <div className="flex items-center gap-6 rounded-xl border border-gray-800 bg-gray-900 px-6 py-4 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">WebSocket</span>
          <span className={`flex items-center gap-2 font-semibold ${STATUS_COLOR[connectionStatus]}`}>
            <span className={`h-2 w-2 rounded-full ${STATUS_DOT[connectionStatus]}`} />
            {connectionStatus.charAt(0).toUpperCase() + connectionStatus.slice(1)}
          </span>
        </div>

        <div className="w-px h-4 bg-gray-700" />

        <div className="flex items-center gap-2">
          <span className="text-gray-400">Camera</span>
          <span className={`font-semibold ${isTracking ? 'text-green-400' : 'text-gray-600'}`}>
            {isTracking ? 'Active' : 'Inactive'}
          </span>
        </div>

        <div className="w-px h-4 bg-gray-700" />

        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="text-gray-400">Lag</span>
          <span className={
            lagMs === null   ? 'text-gray-500' :
            lagMs < 150      ? 'text-green-400' :
            lagMs < 500      ? 'text-yellow-400' :
                               'text-red-400'
          }>
            {lagMs === null ? '—' : `${lagMs} ms`}
          </span>
        </div>

        {gazePoint && (
          <>
            <div className="w-px h-4 bg-gray-700" />
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-gray-400">Gaze</span>
              <span className="text-violet-400">x&nbsp;{gazePoint.x.toFixed(3)}</span>
              <span className="text-violet-400">y&nbsp;{gazePoint.y.toFixed(3)}</span>
            </div>
          </>
        )}
      </div>

      {cameraError && (
        <div className="max-w-md rounded-xl border border-red-800 bg-red-950/40 px-6 py-4 text-sm text-red-300 text-center leading-relaxed">
          {cameraError}
        </div>
      )}

      {gazePoint && (
        <div
          className="pointer-events-none fixed z-50 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-400 opacity-80 ring-2 ring-white/30"
          style={{
            left: `${gazePoint.x * 100}%`,
            top: `${gazePoint.y * 100}%`,
            transition: 'left 50ms linear, top 50ms linear',
          }}
        />
      )}

      {sessionId && <WebcamStreamer sessionId={sessionId} />}
      <HeatmapOverlay />
    </main>
  );
}
