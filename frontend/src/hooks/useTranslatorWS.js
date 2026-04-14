import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useTranslatorWS
 * Manages a single WebSocket connection to the backend /ws/translate endpoint.
 * Exposes helpers to send config, send audio chunks, and flush the buffer.
 */
export function useTranslatorWS({ onTranscript, onTranslation, onError, onStatusChange }) {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);

  const getWsUrl = () => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = import.meta.env.VITE_API_HOST || window.location.host;
    return `${proto}://${host}/ws/translate`;
  };

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < 2) return; // already open/connecting

    const ws = new WebSocket(getWsUrl());
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      onStatusChange?.('connected');
    };

    ws.onclose = () => {
      setConnected(false);
      onStatusChange?.('disconnected');
    };

    ws.onerror = () => {
      onError?.('WebSocket connection error');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'transcript') onTranscript?.(msg);
        else if (msg.type === 'translation') onTranslation?.(msg);
        else if (msg.type === 'error') onError?.(msg.message);
      } catch {
        // ignore malformed messages
      }
    };
  }, [onTranscript, onTranslation, onError, onStatusChange]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
  }, []);

  const sendConfig = useCallback((config) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'config', ...config }));
    }
  }, []);

  const sendAudioChunk = useCallback((arrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(arrayBuffer);
    }
  }, []);

  const flush = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'flush' }));
    }
  }, []);

  // Clean up on unmount
  useEffect(() => () => wsRef.current?.close(), []);

  return { connected, connect, disconnect, sendConfig, sendAudioChunk, flush };
}
