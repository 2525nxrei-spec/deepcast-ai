/**
 * POST /api/stripe/checkout — 高度な異常系テスト
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

const mockStripeRequest = vi.fn();

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: (...args) => mockStripeRequest(...args),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestPost: checkout } = await import('../functions/api/stripe/checkout.js');

describe('POST /api/stripe/checkout — 異常系', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockStripeRequest.mockImplementation(async (endpoint) => {
      if (endpoint === 'customers') return { id: 'cus_mock_123' };
      if (endpoint === 'checkout/sessions') return { id: 'cs_mock_123', client_secret: 'cs_secret_mock' };
      throw new Error('Unknown endpoint');
    });

    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'checkout-adv@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('Stripe顧客作成APIがエラー: 500', async () => {
    mockStripeRequest.mockRejectedValueOnce(new Error('Stripe API error'));

    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(500);
    const json = await parseResponse(res);
    expect(json.error).toContain('決済セッション');
  });

  it('Checkoutセッション作成APIがエラー: 500', async () => {
    // 顧客作成は成功するがセッション作成で失敗
    mockStripeRequest
      .mockResolvedValueOnce({ id: 'cus_mock_fail' })
      .mockRejectedValueOnce(new Error('Session creation failed'));

    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(500);
  });

  it('既にstripe_customer_idがあるユーザー: 顧客作成をスキップ', async () => {
    // ユーザーにstripe_customer_idを設定
    for (const user of env.DB._store.users.values()) {
      user.stripe_customer_id = 'cus_existing_456';
    }

    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(200);

    // customersエンドポイントは呼ばれない（checkout/sessionsのみ）
    const calls = mockStripeRequest.mock.calls;
    expect(calls.some(c => c[0] === 'customers')).toBe(false);
    expect(calls.some(c => c[0] === 'checkout/sessions')).toBe(true);
  });

  it('不正なトークン: 401', async () => {
    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: 'Bearer totally.invalid.token',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});
