import { NextResponse } from 'next/server';
import { headers } from 'next/headers';
import Stripe from 'stripe';
import { prisma } from '@/lib/prisma';
import { confirmPayment, handlePaymentFailure } from '@/lib/services/paymentService';

const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

function getStripe() {
  if (!process.env.STRIPE_SECRET_KEY) {
    throw new Error('Stripe secret key not configured');
  }
  return new Stripe(process.env.STRIPE_SECRET_KEY, {
    apiVersion: '2024-12-18.acacia',
  });
}

/**
 * POST /api/webhooks/stripe
 * Handle Stripe webhook events
 */
export async function POST(request) {
  try {
    const body = await request.text();
    const signature = headers().get('stripe-signature');

    if (!webhookSecret) {
      console.error('Stripe webhook secret not configured');
      return NextResponse.json({ error: 'Webhook not configured' }, { status: 500 });
    }

    let event;

    try {
      event = getStripe().webhooks.constructEvent(body, signature, webhookSecret);
    } catch (err) {
      console.error('Webhook signature verification failed:', err.message);
      return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
    }

    // Log webhook event
    await prisma.webhookEvent.create({
      data: {
        provider: 'stripe',
        eventType: event.type,
        eventId: event.id,
        payload: event,
        processed: false,
      },
    });

    console.log(`Received Stripe webhook: ${event.type}`);

    // Handle the event
    try {
      switch (event.type) {
        case 'checkout.session.completed':
          await handleCheckoutSessionCompleted(event.data.object);
          break;

        case 'checkout.session.async_payment_succeeded':
          await handleAsyncPaymentSucceeded(event.data.object);
          break;

        case 'checkout.session.async_payment_failed':
          await handleAsyncPaymentFailed(event.data.object);
          break;

        case 'payment_intent.succeeded':
          await handlePaymentIntentSucceeded(event.data.object);
          break;

        case 'payment_intent.payment_failed':
          await handlePaymentIntentFailed(event.data.object);
          break;

        default:
          console.log(`Unhandled event type: ${event.type}`);
      }

      // Mark webhook as processed
      await prisma.webhookEvent.updateMany({
        where: { eventId: event.id },
        data: {
          processed: true,
          processedAt: new Date(),
        },
      });
    } catch (error) {
      console.error('Error processing webhook:', error);
      
      // Log error in webhook event
      await prisma.webhookEvent.updateMany({
        where: { eventId: event.id },
        data: {
          processed: false,
          errorMessage: error.message,
        },
      });

      // Return 500 so Stripe retries
      return NextResponse.json({ error: 'Processing failed' }, { status: 500 });
    }

    return NextResponse.json({ received: true });
  } catch (error) {
    console.error('Webhook handler error:', error);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}

/**
 * Handle checkout.session.completed
 */
async function handleCheckoutSessionCompleted(session) {
  const rampSessionId = session.client_reference_id || session.metadata?.rampSessionId;

  if (!rampSessionId) {
    console.error('No ramp session ID in checkout session');
    return;
  }

  const rampSession = await prisma.rampSession.findUnique({
    where: { id: rampSessionId },
  });

  if (!rampSession) {
    console.error(`Ramp session not found: ${rampSessionId}`);
    return;
  }

  // Update ramp session based on payment status
  if (session.payment_status === 'paid') {
    await confirmPayment(rampSessionId, session.payment_intent);
    console.log(`Payment confirmed for session ${rampSessionId}`);
  } else if (session.payment_status === 'unpaid') {
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'PROCESSING',
        paymentStatus: 'processing',
      },
    });
    console.log(`Payment processing for session ${rampSessionId}`);
  }
}

/**
 * Handle checkout.session.async_payment_succeeded
 */
async function handleAsyncPaymentSucceeded(session) {
  const rampSessionId = session.client_reference_id || session.metadata?.rampSessionId;

  if (!rampSessionId) {
    console.error('No ramp session ID in async payment success');
    return;
  }

  await confirmPayment(rampSessionId, session.payment_intent);
  console.log(`Async payment succeeded for session ${rampSessionId}`);
}

/**
 * Handle checkout.session.async_payment_failed
 */
async function handleAsyncPaymentFailed(session) {
  const rampSessionId = session.client_reference_id || session.metadata?.rampSessionId;

  if (!rampSessionId) {
    console.error('No ramp session ID in async payment failure');
    return;
  }

  await handlePaymentFailure(rampSessionId, 'Async payment failed');
  console.log(`Async payment failed for session ${rampSessionId}`);
}

/**
 * Handle payment_intent.succeeded
 */
async function handlePaymentIntentSucceeded(paymentIntent) {
  // Find ramp session by payment intent ID
  const rampSession = await prisma.rampSession.findFirst({
    where: { paymentIntentId: paymentIntent.id },
  });

  if (!rampSession) {
    console.log(`No ramp session found for payment intent ${paymentIntent.id}`);
    return;
  }

  if (rampSession.status === 'PAYMENT_CONFIRMED') {
    console.log(`Payment already confirmed for session ${rampSession.id}`);
    return;
  }

  await confirmPayment(rampSession.id, paymentIntent.id);
  console.log(`Payment intent succeeded for session ${rampSession.id}`);
}

/**
 * Handle payment_intent.payment_failed
 */
async function handlePaymentIntentFailed(paymentIntent) {
  // Find ramp session by payment intent ID
  const rampSession = await prisma.rampSession.findFirst({
    where: { paymentIntentId: paymentIntent.id },
  });

  if (!rampSession) {
    console.log(`No ramp session found for payment intent ${paymentIntent.id}`);
    return;
  }

  const reason = paymentIntent.last_payment_error?.message || 'Payment failed';
  await handlePaymentFailure(rampSession.id, reason);
  console.log(`Payment intent failed for session ${rampSession.id}: ${reason}`);
}
