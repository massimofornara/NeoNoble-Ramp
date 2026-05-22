const { WebSocketServer } = require('ws');
const Redis = require('ioredis');

const port = Number(process.env.WS_GATEWAY_PORT || 8080);
const redisUrl = process.env.REDIS_URL || '';
const wss = new WebSocketServer({ port });
const subscriptions = new WeakMap();

async function subscribe(topic, handler) {
  if (!redisUrl) return async () => undefined;
  const redis = new Redis(redisUrl);
  await redis.subscribe(topic);
  redis.on('message', (_channel, payload) => handler(JSON.parse(payload)));
  return async () => {
    await redis.unsubscribe(topic);
    redis.disconnect();
  };
}

wss.on('connection', (socket) => {
  subscriptions.set(socket, []);
  socket.on('message', async (raw) => {
    try {
      const message = JSON.parse(raw.toString());
      if (message.op !== 'subscribe' || !message.topic) throw new Error('Expected subscribe topic');
      const unsubscribe = await subscribe(message.topic, (payload) => {
        if (socket.readyState === socket.OPEN) socket.send(JSON.stringify(payload));
      });
      subscriptions.get(socket).push(unsubscribe);
      socket.send(JSON.stringify({ type: 'subscribed', topic: message.topic }));
    } catch (error) {
      socket.send(JSON.stringify({ type: 'error', error: error instanceof Error ? error.message : 'Invalid message' }));
    }
  });
  socket.on('close', async () => {
    for (const unsubscribe of subscriptions.get(socket) || []) await unsubscribe();
  });
});

console.log(JSON.stringify({ level: 'info', service: 'ws-gateway', port }));
