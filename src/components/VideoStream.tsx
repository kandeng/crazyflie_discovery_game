import { useState } from 'react';

interface VideoStreamProps {
  streamUrl: string;
}

export default function VideoStream({ streamUrl }: VideoStreamProps) {
  const [status, setStatus] = useState<'loading' | 'connected' | 'error'>('loading');

  return (
    <div className="relative w-full h-full bg-black">
      <img
        src={streamUrl}
        alt="Crazyflie camera"
        className="w-full h-full object-cover"
        onLoad={() => setStatus('connected')}
        onError={() => setStatus('error')}
      />

      {status === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 z-10">
          <div className="w-8 h-8 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mb-3" />
          <span className="text-gray-400 text-sm">Connecting to camera...</span>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 z-10">
          <span className="text-red-400 text-lg mb-2">No Video Signal</span>
          <span className="text-gray-500 text-xs">
            Check that the bridge is running at {streamUrl}
          </span>
          <button
            onClick={() => setStatus('loading')}
            className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg active:bg-blue-700"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
