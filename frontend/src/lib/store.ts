import { create } from 'zustand';
import type { ConnectionStatus } from './websocket';

export interface GazePoint {
  x: number;
  y: number;
}

interface GazeStore {
  isTracking: boolean;
  isCalibrating: boolean;
  connectionStatus: ConnectionStatus;
  cameraError: string | null;
  gazePoint: GazePoint | null;
  lastGazeTs: number | null;

  setIsTracking: (v: boolean) => void;
  setIsCalibrating: (v: boolean) => void;
  setConnectionStatus: (s: ConnectionStatus) => void;
  setCameraError: (e: string | null) => void;
  setGazePoint: (p: GazePoint | null) => void;
  setLastGazeTs: (ts: number) => void;
}

export const useGazeStore = create<GazeStore>((set) => ({
  isTracking: false,
  isCalibrating: false,
  connectionStatus: 'disconnected',
  cameraError: null,
  gazePoint: null,
  lastGazeTs: null,

  setIsTracking: (v) => set({ isTracking: v }),
  setIsCalibrating: (v) => set({ isCalibrating: v }),
  setConnectionStatus: (s) => set({ connectionStatus: s }),
  setCameraError: (e) => set({ cameraError: e }),
  setGazePoint: (p) => set({ gazePoint: p }),
  setLastGazeTs: (ts) => set({ lastGazeTs: ts }),
}));
