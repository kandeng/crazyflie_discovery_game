const host = window.location.hostname;

export const BRIDGE_CONFIG = {
  videoStreamUrl: '/api/stream',
  wsUrl: `ws://${host}:8765`,
};
