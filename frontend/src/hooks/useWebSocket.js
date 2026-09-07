import { useEffect, useRef, useState, useCallback } from 'react';
import { getAuthToken } from '../api/client';

export function useWebSocket(onEvent, enabled = true) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let timeoutId = null;
    let disposed = false;

    const connect = () => {
      if (disposed || !enabled) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const token = getAuthToken();
      if (!token) return;
      const wsUrl = `${protocol}//${window.location.host}/ws/monitoring`;

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (disposed) {
          ws.close(1000, 'Component unmounted');
          return;
        }
        ws.send(JSON.stringify({ type: 'authenticate', token }));
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.event === 'authenticated') {
            setIsConnected(true);
            return;
          }
          if (onEventRef.current) {
            onEventRef.current(parsed);
          }
        } catch {}
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (!disposed) {
          timeoutId = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => ws.close();

      wsRef.current = ws;
    };

    connect();

    return () => {
      disposed = true;
      if (timeoutId) clearTimeout(timeoutId);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    };
  }, [enabled]);

  return { isConnected };
}
