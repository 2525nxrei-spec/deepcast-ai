/**
 * POST /api/stripe/checkout のテスト
 * Stripe APIはモック使用（外部呼び出し禁止）
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

// stripeRequestをモック
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(async (endpoint, method, body) => {
    if (endpoint === 'customers') {
      return { id: 'cus_mock_123' };
    }
    if (endpoint === 'checkout/sessions') {
      return { id: 'cs_mock_123', client_secret: 'cs_secret_mock' };
    }
    throw new Error('Unknown endpoint');
  }),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestPost: checkout } = await import('../functions/api/stripe/checkout.js');

describe('POST /api/stripe/checkout', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'checkout-test@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('正常にCheckoutセッション作成', async () => {
    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.clientSecret).toBe('cs_secret_mock');
  });

  it('認証なし: 401', async () => {
    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout'),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('STRIPE_PRICE_PROが未設定: 500', async () => {
    env.STRIPE_PRICE_PRO = '';
    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(500);
    const json = await parseResponse(res);
    expect(json.error).toContain('Price ID');
  });
});
