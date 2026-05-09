import { useState, useEffect, useRef, useCallback } from 'react';

export interface TelemetryData {
  x: number;
  y: number;
  z: number;
  roll: number;
  pitch: number;
  yaw: number;
  vbat: number;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

export interface CrazyflieCommand {
  action: 'takeoff' | 'land' | 'stop' | 'move';
  height?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  yawrate?: number;
}

const INITIAL_TELEMETRY: TelemetryData = {
  x: 0, y: 0, z: 0,
  roll: 0, pitch: 0, yaw: 0,
  vbat: 0,
};

export function useCrazyflieSocket(wsUrl: string) {
  const [telemetry, setTelemetry] = useState<TelemetryData>(INITIAL_TELEMETRY);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const retryDelayRef = useRef(1000);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('connected');
      retryDelayRef.current = 1000;
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'telemetry') {
          setTelemetry((prev) => {
            const next = { ...prev };
            if (msg.category === 'position') {
              next.x = msg.data.x ?? prev.x;
              next.y = msg.data.y ?? prev.y;
              next.z = msg.data.z ?? prev.z;
            } else if (msg.category === 'attitude') {
              next.roll = msg.data.roll ?? prev.roll;
              next.pitch = msg.data.pitch ?? prev.pitch;
              next.yaw = msg.data.yaw ?? prev.yaw;
            } else if (msg.category === 'battery') {
              next.vbat = msg.data.voltage ?? prev.vbat;
            }
            return next;
          });
        }
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      wsRef.current = null;
      // Exponential backoff reconnect (max 10s)
      retryRef.current = setTimeout(() => {
        retryDelayRef.current = Math.min(retryDelayRef.current * 1.5, 10000);
        connect();
      }, retryDelayRef.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [wsUrl]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(retryRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const sendCommand = useCallback((cmd: CrazyflieCommand) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  return { telemetry, status, sendCommand };
}
