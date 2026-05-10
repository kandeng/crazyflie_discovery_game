import type { TelemetryData, ConnectionStatus } from '../hooks/useCrazyflieSocket';

interface TelemetryOverlayProps {
  telemetry: TelemetryData;
}

function fmt(v: number, decimals = 2): string {
  return v.toFixed(decimals);
}

export default function TelemetryOverlay({ telemetry }: TelemetryOverlayProps) {
  return (
    <div className="absolute bottom-6 left-5 right-5 z-20 pointer-events-none">
      <div className="bg-white/15 backdrop-blur-md rounded-sm px-6 py-7 text-black font-mono text-[11px] leading-relaxed">
        <div className="flex gap-4 justify-center">
          <span>X: <b>{fmt(telemetry.x)}</b></span>
          <span>Y: <b>{fmt(telemetry.y)}</b></span>
          <span>Z: <b>{fmt(telemetry.z)}</b></span>
        </div>
        <div className="flex gap-4 justify-center">
          <span>R: <b>{fmt(telemetry.roll, 1)}</b></span>
          <span>P: <b>{fmt(telemetry.pitch, 1)}</b></span>
          <span>Yaw: <b>{fmt(telemetry.yaw, 1)}</b></span>
          <span>Bat: <b>{fmt(telemetry.vbat, 2)}V</b></span>
        </div>
      </div>
    </div>
  );
}
