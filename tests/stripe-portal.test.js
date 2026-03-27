/**
 * POST /api/stripe/portal のテスト
 * Stripe APIはモック使用
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(async (endpoint) => {
    if (endpoint === 'billing_portal/sessions') {
      return { url: 'https://billing.stripe.com/mock-portal-url' };
    }
    throw new Error('Unknown endpoint');
  }),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestPost: portal } = await import('../functions/api/stripe/portal.js');

describe('POST /api/stripe/portal', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'portal-test@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('stripe_customer_idがない: 400', async () => {
    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('サブスクリプション情報');
  });

  it('認証なし: 401', async () => {
    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal'),
      env,
    });
    expect(res.status).toBe(401);
  });
});
