import { useEffect, useRef, useState, useCallback } from 'react';

export function useWebSocket(onEvent) {
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
      if (disposed) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/monitoring`;

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (disposed) {
          ws.close(1000, 'Component unmounted');
          return;
        }
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (onEventRef.current) {
            onEventRef.current(parsed);
          }
        } catch (err) {
          console.error('Failed to parse WS message', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (!disposed) {
          timeoutId = setTimeout(connect, 3000);
        }
      };

      ws.onerror = (err) => {
        console.error('WS Error:', err);
        ws.close();
      };

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
  }, []);

  return { isConnected };
}
