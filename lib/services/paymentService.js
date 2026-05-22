import Stripe from 'stripe';
import { prisma } from '../prisma';

const PAYMENT_MODE = process.env.PAYMENT_MODE || 'mock';
const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';

let stripeClient = null;
if (PAYMENT_MODE === 'live' && process.env.STRIPE_SECRET_KEY) {
  stripeClient = new Stripe(process.env.STRIPE_SECRET_KEY, {
    apiVersion: '2024-12-18.acacia',
  });
}

/**
 * Payment Provider Interface
 */
class PaymentProvider {
  async createCheckoutSession(session) {
    throw new Error('Not implemented');
  }

  async getSessionStatus(sessionId) {
    throw new Error('Not implemented');
  }

  async handleWebhook(event) {
    throw new Error('Not implemented');
  }
}

/**
 * Stripe Payment Provider
 */
class StripeProvider extends PaymentProvider {
  constructor() {
    super();
    if (!stripeClient) {
      throw new Error('Stripe not configured');
    }
    this.stripe = stripeClient;
  }

  async createCheckoutSession(rampSession) {
    try {
      const session = await this.stripe.checkout.sessions.create({
        payment_method_types: ['card'],
        line_items: [
          {
            price_data: {
              currency: 'eur',
              product_data: {
                name: `${rampSession.type === 'ONRAMP' ? 'Buy' : 'Sell'} ${rampSession.tokens} ${rampSession.tokenSymbol}`,
                description: `${rampSession.type} on ${rampSession.chain}`,
              },
              unit_amount: Math.round(rampSession.amountFiat * 100), // Convert to cents
            },
            quantity: 1,
          },
        ],
        mode: 'payment',
        success_url: `${BASE_URL}/ramp/success?session_id=${rampSession.id}`,
        cancel_url: `${BASE_URL}/ramp/cancel?session_id=${rampSession.id}`,
        client_reference_id: rampSession.id,
        metadata: {
          rampSessionId: rampSession.id,
          type: rampSession.type,
          tokenSymbol: rampSession.tokenSymbol,
        },
      });

      return {
        sessionId: session.id,
        checkoutUrl: session.url,
        status: 'created',
      };
    } catch (error) {
      console.error('Stripe checkout session creation failed:', error);
      throw new Error(`Failed to create Stripe session: ${error.message}`);
    }
  }

  async getSessionStatus(sessionId) {
    try {
      const session = await this.stripe.checkout.sessions.retrieve(sessionId);
      return {
        status: session.payment_status,
        paymentIntentId: session.payment_intent,
      };
    } catch (error) {
      console.error('Failed to retrieve Stripe session:', error);
      throw error;
    }
  }

  async constructWebhookEvent(body, signature) {
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
    if (!webhookSecret) {
      throw new Error('Stripe webhook secret not configured');
    }

    try {
      return this.stripe.webhooks.constructEvent(body, signature, webhookSecret);
    } catch (error) {
      console.error('Webhook signature verification failed:', error);
      throw error;
    }
  }
}

/**
 * Mock Payment Provider (for testing)
 */
class MockProvider extends PaymentProvider {
  async createCheckoutSession(rampSession) {
    const mockSessionId = `mock_cs_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    return {
      sessionId: mockSessionId,
      checkoutUrl: `${BASE_URL}/ramp/mock-checkout?session_id=${rampSession.id}&mock_payment_id=${mockSessionId}`,
      status: 'created',
    };
  }

  async getSessionStatus(sessionId) {
    // Mock always returns success after creation
    return {
      status: 'paid',
      paymentIntentId: `mock_pi_${sessionId}`,
    };
  }

  async handleMockPayment(rampSessionId, success = true) {
    const session = await prisma.rampSession.findUnique({
      where: { id: rampSessionId },
    });

    if (!session) {
      throw new Error('Session not found');
    }

    const newStatus = success ? 'PAYMENT_CONFIRMED' : 'FAILED';
    
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: newStatus,
        paymentStatus: success ? 'paid' : 'failed',
        lastProcessedAt: new Date(),
      },
    });

    return { success, status: newStatus };
  }
}

/**
 * Get the appropriate payment provider
 */
export function getPaymentProvider() {
  if (PAYMENT_MODE === 'live') {
    return new StripeProvider();
  }
  return new MockProvider();
}

/**
 * Create a payment session for a ramp transaction
 */
export async function createPaymentSession(rampSession) {
  const provider = getPaymentProvider();
  
  try {
    const result = await provider.createCheckoutSession(rampSession);
    
    // Update ramp session with payment details
    await prisma.rampSession.update({
      where: { id: rampSession.id },
      data: {
        paymentProvider: PAYMENT_MODE,
        paymentSessionId: result.sessionId,
        status: 'AWAITING_PAYMENT',
        checkoutUrl: result.checkoutUrl,
      },
    });

    return result;
  } catch (error) {
    console.error('Payment session creation failed:', error);
    
    await prisma.rampSession.update({
      where: { id: rampSession.id },
      data: {
        status: 'FAILED',
        errorMessage: error.message,
      },
    });

    throw error;
  }
}

/**
 * Process payment confirmation
 */
export async function confirmPayment(rampSessionId, paymentIntentId) {
  try {
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'PAYMENT_CONFIRMED',
        paymentIntentId,
        paymentStatus: 'paid',
        lastProcessedAt: new Date(),
      },
    });

    console.log(`Payment confirmed for session ${rampSessionId}`);
    return true;
  } catch (error) {
    console.error('Failed to confirm payment:', error);
    throw error;
  }
}

/**
 * Handle payment failure
 */
export async function handlePaymentFailure(rampSessionId, reason) {
  try {
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'FAILED',
        paymentStatus: 'failed',
        errorMessage: reason,
        lastProcessedAt: new Date(),
      },
    });

    console.log(`Payment failed for session ${rampSessionId}: ${reason}`);
    return true;
  } catch (error) {
    console.error('Failed to handle payment failure:', error);
    throw error;
  }
}

export { MockProvider, StripeProvider };