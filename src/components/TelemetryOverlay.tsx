import type { TelemetryData, ConnectionStatus } from '../hooks/useCrazyflieSocket';

interface TelemetryOverlayProps {
  telemetry: TelemetryData;
  wsStatus: ConnectionStatus;
}

function fmt(v: number, decimals = 2): string {
  return v.toFixed(decimals);
}

export default function TelemetryOverlay({ telemetry, wsStatus }: TelemetryOverlayProps) {
  const statusColor =
    wsStatus === 'connected' ? 'text-green-400' :
    wsStatus === 'connecting' ? 'text-yellow-400' :
    'text-red-400';

  const statusLabel =
    wsStatus === 'connected' ? 'WS: OK' :
    wsStatus === 'connecting' ? 'WS: ...' :
    'WS: OFF';

  return (
    <div className="absolute bottom-4 left-3 right-3 z-20 pointer-events-none">
      <div className="bg-black/60 backdrop-blur-sm rounded-lg px-3 py-2 text-white font-mono text-[11px] leading-relaxed">
        <div className="flex gap-4">
          <span>X: <b>{fmt(telemetry.x)}</b></span>
          <span>Y: <b>{fmt(telemetry.y)}</b></span>
          <span>Z: <b>{fmt(telemetry.z)}</b></span>
        </div>
        <div className="flex gap-4">
          <span>R: <b>{fmt(telemetry.roll, 1)}</b></span>
          <span>P: <b>{fmt(telemetry.pitch, 1)}</b></span>
          <span>Yaw: <b>{fmt(telemetry.yaw, 1)}</b></span>
        </div>
        <div className="flex justify-between">
          <span>Bat: <b>{fmt(telemetry.vbat, 2)}V</b></span>
          <span className={statusColor}>{statusLabel}</span>
        </div>
      </div>
    </div>
  );
}
