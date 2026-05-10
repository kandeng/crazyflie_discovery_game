import { useState, useCallback } from 'react';
import { Joystick, ChatPanel } from 'mobile_game_pwa';
import VideoStream from './components/VideoStream';
import TelemetryOverlay from './components/TelemetryOverlay';
import { useCrazyflieSocket } from './hooks/useCrazyflieSocket';
import { BRIDGE_CONFIG } from './config';

export default function App() {
  const { telemetry, status, sendCommand } = useCrazyflieSocket(BRIDGE_CONFIG.wsUrl);

  const [toolboxOpen, setToolboxOpen] = useState(false);
  const [chatHeight, setChatHeight] = useState(30);

  /* ---- Joystick -> WebSocket command mapping ---- */

  const onMove = useCallback((vx: number, vy: number) => {
    sendCommand({ action: 'move', vx, vy, vz: 0, yawrate: 0 });
  }, [sendCommand]);

  const onRotate = useCallback((vyaw: number) => {
    sendCommand({ action: 'move', vx: 0, vy: 0, vz: 0, yawrate: vyaw });
  }, [sendCommand]);

  const onHeight = useCallback((vz: number) => {
    sendCommand({ action: 'move', vx: 0, vy: 0, vz, yawrate: 0 });
  }, [sendCommand]);

  const onStop = useCallback(() => {
    sendCommand({ action: 'stop' });
  }, [sendCommand]);

  const onFocal = useCallback((_vf: number) => {
    // No camera zoom on physical drone
  }, []);

  const handleDragDelta = useCallback((deltaVh: number) => {
    setChatHeight((h) => Math.max(15, Math.min(60, h + deltaVh)));
  }, []);

  return (
    <div className="flex flex-col w-screen overflow-hidden bg-gray-900 select-none" style={{ height: '100dvh' }}>
      {/* Main viewport: video + joystick + telemetry */}
      <div className="relative w-full flex-shrink-0 touch-none" style={{ height: `${100 - chatHeight}vh` }}>
        <VideoStream streamUrl={BRIDGE_CONFIG.videoStreamUrl} />

        {/* Takeoff / Land buttons */}
        <div className="absolute top-3 left-3 z-30 flex gap-2">
          <button
            onClick={() => sendCommand({ action: 'takeoff', height: 0.5 })}
            className="px-3 py-1.5 bg-green-600/80 backdrop-blur-sm text-white text-xs font-medium rounded-lg active:bg-green-700 pointer-events-auto"
          >
            Takeoff
          </button>
          <button
            onClick={() => sendCommand({ action: 'land' })}
            className="px-3 py-1.5 bg-red-600/80 backdrop-blur-sm text-white text-xs font-medium rounded-lg active:bg-red-700 pointer-events-auto"
          >
            Land
          </button>
        </div>

        {/* Connection status badge */}
        <div className="absolute top-3 right-3 z-20">
          <div className={`px-2 py-1 rounded-full text-[10px] font-medium backdrop-blur-sm ${
            status === 'connected' ? 'bg-green-500/70 text-white' :
            status === 'connecting' ? 'bg-yellow-500/70 text-white' :
            'bg-red-500/70 text-white'
          }`}>
            {status === 'connected' ? 'Connected' :
             status === 'connecting' ? 'Connecting...' :
             'Disconnected'}
          </div>
        </div>

        {/* Telemetry overlay at bottom of viewport */}
        <TelemetryOverlay telemetry={telemetry} />

        {/* Joystick overlay */}
        <div className="absolute inset-0 z-20 pointer-events-none">
          <Joystick
            onMove={onMove}
            onRotate={onRotate}
            onHeight={onHeight}
            onFocal={onFocal}
            onStop={onStop}
          />
        </div>
      </div>

      {/* Chat panel */}
      <div className="relative w-full flex-grow overflow-hidden" style={{ height: `${chatHeight}vh` }}>
        <ChatPanel
          toolboxOpen={toolboxOpen}
          onToggleToolbox={() => setToolboxOpen((o) => !o)}
          onDragDelta={handleDragDelta}
        />
      </div>
    </div>
  );
}
