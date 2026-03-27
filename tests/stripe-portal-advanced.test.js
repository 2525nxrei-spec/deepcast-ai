/**
 * POST /api/stripe/portal — 高度な異常系テスト
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

const mockStripeRequest = vi.fn();

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: (...args) => mockStripeRequest(...args),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestPost: portal } = await import('../functions/api/stripe/portal.js');

describe('POST /api/stripe/portal — 異常系', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockStripeRequest.mockImplementation(async (endpoint) => {
      if (endpoint === 'billing_portal/sessions') {
        return { url: 'https://billing.stripe.com/mock-portal' };
      }
      throw new Error('Unknown endpoint');
    });

    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'portal-adv@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('stripe_customer_idあり: ポータルURL取得成功', async () => {
    // ユーザーにstripe_customer_idを設定
    for (const user of env.DB._store.users.values()) {
      user.stripe_customer_id = 'cus_portal_123';
    }

    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.portal_url).toContain('stripe.com');
  });

  it('Stripe APIがエラー: 500', async () => {
    for (const user of env.DB._store.users.values()) {
      user.stripe_customer_id = 'cus_portal_err';
    }

    mockStripeRequest.mockRejectedValueOnce(new Error('Stripe API failure'));

    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(500);
    const json = await parseResponse(res);
    expect(json.error).toContain('ポータル');
  });

  it('不正なトークン: 401', async () => {
    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: 'Bearer invalid.jwt.here',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});
