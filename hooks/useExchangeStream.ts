'use client';

import { useEffect, useState } from 'react';

export function useExchangeStream<T = unknown>(topic: string, enabled = true) {
  const [messages, setMessages] = useState<T[]>([]);
  const [status, setStatus] = useState<'idle' | 'open' | 'closed' | 'error'>('idle');

  useEffect(() => {
    if (!enabled || !topic) return;
    const url = process.env.NEXT_PUBLIC_WS_GATEWAY_URL || 'ws://localhost:8080';
    const socket = new WebSocket(url);
    socket.onopen = () => {
      setStatus('open');
      socket.send(JSON.stringify({ op: 'subscribe', topic }));
    };
    socket.onmessage = (event) => setMessages((current) => [JSON.parse(event.data) as T, ...current].slice(0, 200));
    socket.onerror = () => setStatus('error');
    socket.onclose = () => setStatus('closed');
    return () => socket.close();
  }, [enabled, topic]);

  return { messages, status };
}
