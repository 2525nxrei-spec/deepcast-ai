/**
 * 課金系テスト — checkout / webhook / billing status
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';
import { createTestEnv, createTestUser, createContext, parseResponse } from './helpers.js';
import { onRequestPost as checkout } from '../functions/api/stripe/checkout.js';
import { onRequestPost as webhook } from '../functions/api/stripe/webhook.js';
import { onRequestGet as billingStatus } from '../functions/api/billing/status.js';

let mf, db, env;

beforeAll(async () => {
  ({ mf, db, env } = await createTestEnv());
});

afterAll(async () => {
  await mf.dispose();
});

beforeEach(async () => {
  await db.exec('DELETE FROM users');
  await db.exec('DELETE FROM webhooks_log');
});

// === POST /api/stripe/checkout ===

describe('POST /api/stripe/checkout', () => {
  it('認証済みユーザー — Checkout Sessionが作成される', async () => {
    const user = await createTestUser(db, { email: 'pro@example.com' });

    // stripeRequestをモック: customers POST → customer作成、checkout/sessions POST → session作成
    const stripeModule = await import('../functions/lib/stripe.js');
    const originalStripeRequest = stripeModule.stripeRequest;

    // globalのfetchをモックしてStripe APIをシミュレート
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (url, options) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('api.stripe.com/v1/customers') && options?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'cus_test_123', object: 'customer' }));
      }
      if (urlStr.includes('api.stripe.com/v1/checkout/sessions') && options?.method === 'POST') {
        return new Response(JSON.stringify({
          id: 'cs_test_session',
          url: 'https://checkout.stripe.com/pay/cs_test_session',
        }));
      }
      return originalFetch(url, options);
    });

    try {
      const request = new Request('https://deepcast-ai.com/api/stripe/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user.token}`,
        },
      });

      const res = await checkout(createContext(request, env));
      const { status, body } = await parseResponse(res);

      expect(status).toBe(200);
      expect(body.ok).toBe(true);
      expect(body.url).toContain('checkout.stripe.com');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('Proユーザー — 重複決済を拒否する', async () => {
    const user = await createTestUser(db, { email: 'already-pro@example.com', plan: 'pro' });

    const request = new Request('https://deepcast-ai.com/api/stripe/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${user.token}`,
      },
    });

    const res = await checkout(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('すでにPro');
  });

  it('未認証 — 401を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/stripe/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    const res = await checkout(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('認証');
  });

  it('STRIPE_SECRET_KEY未設定 — 500を返す', async () => {
    const user = await createTestUser(db, { email: 'nokey@example.com' });
    const envNoKey = { ...env, STRIPE_SECRET_KEY: '' };

    const request = new Request('https://deepcast-ai.com/api/stripe/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${user.token}`,
      },
    });

    const res = await checkout(createContext(request, envNoKey));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(500);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('決済サービス');
  });

  it('STRIPE_PRICE_PRO未設定 — 500を返す', async () => {
    const user = await createTestUser(db, { email: 'noprice@example.com' });
    const envNoPrice = { ...env, STRIPE_PRICE_PRO: '' };

    const request = new Request('https://deepcast-ai.com/api/stripe/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${user.token}`,
      },
    });

    const res = await checkout(createContext(request, envNoPrice));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(500);
    expect(body.ok).toBe(false);
  });
});

// === POST /api/stripe/webhook ===

describe('POST /api/stripe/webhook', () => {
  /**
   * Stripe署名を生成するヘルパー
   * verifyStripeSignature と同じHMAC-SHA256ロジック
   */
  async function createStripeSignature(payload, secret) {
    const timestamp = Math.floor(Date.now() / 1000);
    const signedPayload = `${timestamp}.${payload}`;
    const encoder = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
      'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
    );
    const signatureBuffer = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(signedPayload));
    const sig = Array.from(new Uint8Array(signatureBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
    return `t=${timestamp},v1=${sig}`;
  }

  it('checkout.session.completed — ユーザーがProにアップグレードされる', async () => {
    const user = await createTestUser(db, {
      email: 'webhook-pro@example.com',
      stripe_customer_id: 'cus_webhook_1',
    });

    const event = {
      id: 'evt_checkout_completed_1',
      type: 'checkout.session.completed',
      data: {
        object: {
          id: 'cs_test_1',
          customer: 'cus_webhook_1',
          subscription: 'sub_test_1',
          metadata: { user_id: user.id },
        },
      },
    };
    const payload = JSON.stringify(event);
    const signature = await createStripeSignature(payload, env.STRIPE_WEBHOOK_SECRET);

    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': signature,
      },
      body: payload,
    });

    const res = await webhook(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.received).toBe(true);

    // DBでplanがproになっていることを確認
    const updated = await db.prepare('SELECT plan, stripe_subscription_id FROM users WHERE id = ?').bind(user.id).first();
    expect(updated.plan).toBe('pro');
    expect(updated.stripe_subscription_id).toBe('sub_test_1');
  });

  it('customer.subscription.deleted — ユーザーがFreeにダウングレードされる', async () => {
    const user = await createTestUser(db, {
      email: 'webhook-cancel@example.com',
      plan: 'pro',
      stripe_customer_id: 'cus_webhook_2',
      stripe_subscription_id: 'sub_cancel_1',
    });

    const event = {
      id: 'evt_sub_deleted_1',
      type: 'customer.subscription.deleted',
      data: {
        object: {
          id: 'sub_cancel_1',
          customer: 'cus_webhook_2',
          status: 'canceled',
        },
      },
    };
    const payload = JSON.stringify(event);
    const signature = await createStripeSignature(payload, env.STRIPE_WEBHOOK_SECRET);

    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': signature,
      },
      body: payload,
    });

    const res = await webhook(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.received).toBe(true);

    // Freeにダウングレードされていること
    const updated = await db.prepare('SELECT plan, stripe_subscription_id FROM users WHERE id = ?').bind(user.id).first();
    expect(updated.plan).toBe('free');
    expect(updated.stripe_subscription_id).toBeNull();
  });

  it('無効な署名 — 400を返す', async () => {
    const event = { id: 'evt_bad_sig', type: 'checkout.session.completed', data: { object: {} } };
    const payload = JSON.stringify(event);

    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': 't=1234567890,v1=invalidsignature',
      },
      body: payload,
    });

    const res = await webhook(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('署名検証');
  });

  it('冪等性 — 同じイベントIDの二重処理を防ぐ', async () => {
    const user = await createTestUser(db, {
      email: 'idempotent@example.com',
      stripe_customer_id: 'cus_idem_1',
    });

    const event = {
      id: 'evt_idempotent_1',
      type: 'checkout.session.completed',
      data: {
        object: {
          id: 'cs_idem_1',
          customer: 'cus_idem_1',
          subscription: 'sub_idem_1',
          metadata: { user_id: user.id },
        },
      },
    };
    const payload = JSON.stringify(event);
    const signature = await createStripeSignature(payload, env.STRIPE_WEBHOOK_SECRET);

    const makeRequest = () => new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': signature,
      },
      body: payload,
    });

    // 1回目
    await webhook(createContext(makeRequest(), env));

    // 2回目（冪等性で処理済みとして返る）
    const res2 = await webhook(createContext(makeRequest(), env));
    const { status, body } = await parseResponse(res2);

    expect(status).toBe(200);
    expect(body.received).toBe(true);
  });

  it('STRIPE_WEBHOOK_SECRET未設定 — 500を返す', async () => {
    const envNoSecret = { ...env, STRIPE_WEBHOOK_SECRET: '' };

    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': 't=123,v1=abc',
      },
      body: '{}',
    });

    const res = await webhook(createContext(request, envNoSecret));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(500);
    expect(body.ok).toBe(false);
  });
});

// === GET /api/billing/status ===

describe('GET /api/billing/status', () => {
  it('Freeユーザー — plan=freeが返る', async () => {
    const user = await createTestUser(db, { email: 'free-user@example.com', plan: 'free' });

    const request = new Request('https://deepcast-ai.com/api/billing/status', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await billingStatus(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.plan).toBe('free');
    expect(body.subscription).toBeNull();
  });

  it('Proユーザー（サブスクリプションID無し） — plan=proでsubscription=null', async () => {
    const user = await createTestUser(db, { email: 'pro-nosub@example.com', plan: 'pro' });

    const request = new Request('https://deepcast-ai.com/api/billing/status', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await billingStatus(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.plan).toBe('pro');
    expect(body.subscription).toBeNull();
  });

  it('未認証 — 401を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/billing/status', {
      method: 'GET',
    });

    const res = await billingStatus(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
  });
});
