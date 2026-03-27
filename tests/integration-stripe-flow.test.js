/**
 * Stripe決済フロー統合テスト
 * 登録 → Checkout → Webhook(Pro化) → Billing確認 → Portal → 解約 の完全フロー
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

const mockStripeRequest = vi.fn();

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: (...args) => mockStripeRequest(...args),
  verifyStripeSignature: vi.fn(async (payload) => JSON.parse(payload)),
}));

const { onRequestPost: checkout } = await import('../functions/api/stripe/checkout.js');
const { onRequestPost: webhook } = await import('../functions/api/stripe/webhook.js');
const { onRequestGet: billingStatus } = await import('../functions/api/billing/status.js');
const { onRequestPost: portal } = await import('../functions/api/stripe/portal.js');

function createWebhookRequest(event) {
  return new Request('https://deepcast-ai.com/api/stripe/webhook', {
    method: 'POST',
    headers: {
      'stripe-signature': 't=1234567890,v1=mock',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(event),
  });
}

describe('Stripe決済フロー統合テスト', () => {
  let env;
  let validToken;
  let userId;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockStripeRequest.mockImplementation(async (endpoint) => {
      if (endpoint === 'customers') return { id: 'cus_flow_123' };
      if (endpoint === 'checkout/sessions') return { id: 'cs_flow', client_secret: 'secret_flow' };
      if (endpoint.startsWith('subscriptions/')) return {
        id: 'sub_flow_123', status: 'active',
        current_period_end: 1700000000, cancel_at_period_end: false,
      };
      if (endpoint === 'billing_portal/sessions') return { url: 'https://billing.stripe.com/portal' };
      throw new Error('Unknown: ' + endpoint);
    });

    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'flow-test@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
    userId = json.user.id;
  });

  it('完全フロー: 登録→Checkout→Webhook(Pro化)→Billing確認→Portal→解約', async () => {
    // 1. Checkout作成
    const checkoutRes = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(checkoutRes.status).toBe(200);
    const checkoutJson = await parseResponse(checkoutRes);
    expect(checkoutJson.clientSecret).toBe('secret_flow');

    // 2. Webhook: checkout.session.completed
    const checkoutEvent = {
      id: 'evt_flow_checkout',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: userId },
          subscription: 'sub_flow_123',
          customer: 'cus_flow_123',
        },
      },
    };
    const webhookRes = await webhook({
      request: createWebhookRequest(checkoutEvent),
      env,
    });
    expect(webhookRes.status).toBe(200);

    // ユーザーがProに
    const user = env.DB._store.users.get(userId);
    expect(user.plan).toBe('pro');
    expect(user.stripe_subscription_id).toBe('sub_flow_123');

    // 3. Billing status確認
    const billingRes = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(billingRes.status).toBe(200);
    const billingJson = await parseResponse(billingRes);
    expect(billingJson.plan).toBe('pro');
    expect(billingJson.subscription).not.toBeNull();

    // 4. Portal URL取得
    const portalRes = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(portalRes.status).toBe(200);
    const portalJson = await parseResponse(portalRes);
    expect(portalJson.portal_url).toContain('stripe.com');

    // 5. Webhook: subscription.deleted (解約)
    const deleteEvent = {
      id: 'evt_flow_delete',
      type: 'customer.subscription.deleted',
      data: {
        object: {
          id: 'sub_flow_123',
          customer: 'cus_flow_123',
        },
      },
    };
    const deleteWebhookRes = await webhook({
      request: createWebhookRequest(deleteEvent),
      env,
    });
    expect(deleteWebhookRes.status).toBe(200);

    // ユーザーがfreeに戻る
    const userAfter = env.DB._store.users.get(userId);
    expect(userAfter.plan).toBe('free');
    expect(userAfter.stripe_subscription_id).toBeNull();
  });
});
