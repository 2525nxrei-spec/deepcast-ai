/**
 * GET /api/billing/status — 高度なテスト
 * Proユーザーのサブスク情報取得、Stripe APIエラー時のフォールバック
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

const mockStripeRequest = vi.fn();

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: (...args) => mockStripeRequest(...args),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestGet: billingStatus } = await import('../functions/api/billing/status.js');

describe('GET /api/billing/status — 詳細テスト', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockStripeRequest.mockImplementation(async (endpoint) => {
      if (endpoint.startsWith('subscriptions/')) {
        return {
          id: 'sub_mock_456',
          status: 'active',
          current_period_end: 1700000000,
          cancel_at_period_end: false,
        };
      }
      throw new Error('Unknown endpoint');
    });

    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'billing-adv@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('Proユーザー（サブスク情報あり）: subscription詳細を返す', async () => {
    // ユーザーをPro状態に
    for (const user of env.DB._store.users.values()) {
      user.plan = 'pro';
      user.stripe_subscription_id = 'sub_billing_test';
    }

    const res = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.plan).toBe('pro');
    expect(json.subscription).not.toBeNull();
    expect(json.subscription.id).toBe('sub_mock_456');
    expect(json.subscription.status).toBe('active');
    expect(json.subscription.next_billing_date).toBeDefined();
  });

  it('Proユーザーだがstripe_subscription_idがnull: subscriptionはnull', async () => {
    for (const user of env.DB._store.users.values()) {
      user.plan = 'pro';
      user.stripe_subscription_id = null;
    }

    const res = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.plan).toBe('pro');
    expect(json.subscription).toBeNull();
  });

  it('Stripe APIエラー時: planは返すがsubscriptionはnull', async () => {
    for (const user of env.DB._store.users.values()) {
      user.plan = 'pro';
      user.stripe_subscription_id = 'sub_err_test';
    }

    mockStripeRequest.mockRejectedValueOnce(new Error('Stripe timeout'));

    const res = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.plan).toBe('pro');
    expect(json.subscription).toBeNull();
  });

  it('STRIPE_SECRET_KEYがない場合: subscriptionはnull', async () => {
    for (const user of env.DB._store.users.values()) {
      user.plan = 'pro';
      user.stripe_subscription_id = 'sub_no_key';
    }

    env.STRIPE_SECRET_KEY = '';

    const res = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.plan).toBe('pro');
    expect(json.subscription).toBeNull();
  });

  it('cancel_at_period_end: trueの場合もデータを正しく返す', async () => {
    for (const user of env.DB._store.users.values()) {
      user.plan = 'pro';
      user.stripe_subscription_id = 'sub_cancel_end';
    }

    mockStripeRequest.mockResolvedValueOnce({
      id: 'sub_cancel_end',
      status: 'active',
      current_period_end: 1700000000,
      cancel_at_period_end: true,
    });

    const res = await billingStatus({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.subscription.cancel_at_period_end).toBe(true);
  });
});
