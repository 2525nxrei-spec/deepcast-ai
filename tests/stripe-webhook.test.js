/**
 * POST /api/stripe/webhook のテスト
 * Stripe署名検証はモック使用（外部API呼び出し禁止）
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createMockEnv, parseResponse } from './helpers.js';

// verifyStripeSignatureをモックして署名検証をスキップ
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(),
  verifyStripeSignature: vi.fn(async (payload) => {
    // ペイロードをそのままパースして返す（署名検証はスキップ）
    return JSON.parse(payload);
  }),
}));

const { onRequestPost: webhook } = await import('../functions/api/stripe/webhook.js');

function createWebhookRequest(event) {
  return new Request('https://deepcast-ai.com/api/stripe/webhook', {
    method: 'POST',
    headers: {
      'stripe-signature': 't=1234567890,v1=mock_signature',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(event),
  });
}

describe('POST /api/stripe/webhook', () => {
  let env;

  beforeEach(() => {
    env = createMockEnv([{
      id: 'user-1',
      email: 'webhook-user@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_webhook_123',
      stripe_subscription_id: null,
    }]);
  });

  it('checkout.session.completed: プランをproに更新', async () => {
    const event = {
      id: 'evt_checkout_1',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: 'user-1' },
          subscription: 'sub_new_123',
          customer: 'cus_webhook_123',
        },
      },
    };

    const res = await webhook({
      request: createWebhookRequest(event),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.received).toBe(true);

    // DBが更新されたか確認
    const user = await env.DB.prepare('SELECT * FROM users WHERE id = ?').bind('user-1').first();
    expect(user.plan).toBe('pro');
    expect(user.stripe_subscription_id).toBe('sub_new_123');
  });

  it('customer.subscription.updated: activeでpro維持', async () => {
    // まずproにしておく
    env.DB._store.users.get('user-1').plan = 'pro';
    env.DB._store.users.get('user-1').stripe_subscription_id = 'sub_old';

    const event = {
      id: 'evt_sub_update_1',
      type: 'customer.subscription.updated',
      data: {
        object: {
          id: 'sub_updated_123',
          status: 'active',
          customer: 'cus_webhook_123',
        },
      },
    };

    const res = await webhook({
      request: createWebhookRequest(event),
      env,
    });

    expect(res.status).toBe(200);
    const user = env.DB._store.users.get('user-1');
    expect(user.plan).toBe('pro');
    expect(user.stripe_subscription_id).toBe('sub_updated_123');
  });

  it('customer.subscription.deleted: freeに戻す', async () => {
    env.DB._store.users.get('user-1').plan = 'pro';
    env.DB._store.users.get('user-1').stripe_subscription_id = 'sub_old';

    const event = {
      id: 'evt_sub_delete_1',
      type: 'customer.subscription.deleted',
      data: {
        object: {
          id: 'sub_old',
          customer: 'cus_webhook_123',
        },
      },
    };

    const res = await webhook({
      request: createWebhookRequest(event),
      env,
    });

    expect(res.status).toBe(200);
    const user = env.DB._store.users.get('user-1');
    expect(user.plan).toBe('free');
    expect(user.stripe_subscription_id).toBeNull();
  });

  it('冪等性: 同じイベントIDは2回目は即return', async () => {
    const event = {
      id: 'evt_idempotent_1',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: 'user-1' },
          subscription: 'sub_123',
          customer: 'cus_webhook_123',
        },
      },
    };

    // 1回目
    await webhook({ request: createWebhookRequest(event), env });

    // 2回目（冪等性で即return）
    const res2 = await webhook({ request: createWebhookRequest(event), env });
    expect(res2.status).toBe(200);
    const json = await parseResponse(res2);
    expect(json.received).toBe(true);
  });

  it('STRIPE_WEBHOOK_SECRET未設定: 500', async () => {
    env.STRIPE_WEBHOOK_SECRET = '';
    const event = { id: 'evt_1', type: 'test', data: { object: {} } };
    const res = await webhook({
      request: createWebhookRequest(event),
      env,
    });
    expect(res.status).toBe(500);
  });

  it('invoice.payment_failed: 200（ログのみ）', async () => {
    const event = {
      id: 'evt_payment_fail_1',
      type: 'invoice.payment_failed',
      data: {
        object: {
          customer: 'cus_webhook_123',
          attempt_count: 2,
        },
      },
    };

    const res = await webhook({
      request: createWebhookRequest(event),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.received).toBe(true);
  });
});
