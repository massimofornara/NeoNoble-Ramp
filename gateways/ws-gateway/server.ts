import { WebSocketServer } from 'ws';
import { subscribeStream } from '@/lib/streaming/pubsub';
import type { StreamTopic } from '@/types/tier1';

type ClientSubscription = {
  unsubscribe: () => void | Promise<void>;
};

const port = Number(process.env.WS_GATEWAY_PORT || 8080);
const wss = new WebSocketServer({ port });
const subscriptions = new WeakMap<object, ClientSubscription[]>();

wss.on('connection', (socket) => {
  subscriptions.set(socket, []);
  socket.on('message', async (raw) => {
    try {
      const message = JSON.parse(raw.toString()) as { op: string; topic: StreamTopic };
      if (message.op !== 'subscribe') throw new Error('Only subscribe op is supported');
      const rawUnsubscribe = await subscribeStream(message.topic, (payload) => {
        if (socket.readyState === socket.OPEN) socket.send(JSON.stringify(payload));
      });
      const unsubscribe = async () => {
        await rawUnsubscribe();
      };
      subscriptions.get(socket)?.push({ unsubscribe });
      socket.send(JSON.stringify({ type: 'subscribed', topic: message.topic }));
    } catch (error) {
      socket.send(JSON.stringify({ type: 'error', error: error instanceof Error ? error.message : 'Invalid message' }));
    }
  });
  socket.on('close', async () => {
    for (const sub of subscriptions.get(socket) || []) await sub.unsubscribe();
  });
});

console.log(JSON.stringify({ level: 'info', service: 'ws-gateway', port }));
