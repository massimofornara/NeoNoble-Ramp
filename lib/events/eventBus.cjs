const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();

async function publishTransactionEvent(transactionId, eventType, payload = {}) {
  const event = await prisma.transactionEvent.create({
    data: {
      transactionId,
      eventType,
      payload,
    },
  });

  console.log(
    JSON.stringify({
      event: eventType,
      transactionId,
      eventId: event.id,
      payload,
    }),
  );

  return event;
}

module.exports = {
  publishTransactionEvent,
};
