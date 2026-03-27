/**
 * GET /api/billing/status のテスト
 * Stripe APIはモックし、実際の外部呼び出しは行わない
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

// stripeRequestをモック
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(async (endpoint) => {
    if (endpoint.startsWith('subscriptions/')) {
      return {
        id: 'sub_mock_123',
        status: 'active',
        current_period_end: 1700000000,
        cancel_at_period_end: false,
      };
    }
    throw new Error('Unknown endpoint');
  }),
  verifyStripeSignature: vi.fn(),
}));

// モック後にインポート
const { onRequestGet } = await import('../functions/api/billing/status.js');

describe('GET /api/billing/status', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'billing-test@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('フリープランユーザー: subscriptionはnull', async () => {
    const res = await onRequestGet({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.plan).toBe('free');
    expect(json.subscription).toBeNull();
  });

  it('認証なし: 401', async () => {
    const res = await onRequestGet({
      request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status'),
      env,
    });
    expect(res.status).toBe(401);
  });
});
