/**
 * stripeRequest 詳細テスト
 * GETリクエストにパラメータ付き、配列パラメータ、エラーメッセージなし、
 * ネットワークエラー等の追加テスト
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const originalFetch = globalThis.fetch;

describe('lib/stripe.js — stripeRequest 詳細テスト', () => {
  let stripeRequest;

  beforeEach(async () => {
    vi.resetModules();
    globalThis.fetch = vi.fn();
    const mod = await import('../functions/lib/stripe.js');
    stripeRequest = mod.stripeRequest;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('GETリクエストにbodyパラメータ: URLクエリに付与', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ data: [{ id: 'sub_1' }] }),
    });

    await stripeRequest('subscriptions', 'GET', { customer: 'cus_123', status: 'active' }, 'sk_test');

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('customer=cus_123');
    expect(url).toContain('status=active');
    expect(options.body).toBeUndefined();
  });

  it('配列パラメータのフラット化', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'cs_123' }),
    });

    await stripeRequest('checkout/sessions', 'POST', {
      'line_items': [{ price: 'price_123', quantity: 1 }],
    }, 'sk_test');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toContain('line_items');
  });

  it('Stripe APIエラーにmessageがない場合: デフォルトメッセージ', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({
        error: { type: 'api_error' },
      }),
    });

    await expect(stripeRequest('test', 'POST', {}, 'sk_test'))
      .rejects.toThrow('Stripe APIエラー');
  });

  it('fetchがネットワークエラーをthrow: そのままエラーが伝播', async () => {
    globalThis.fetch.mockRejectedValueOnce(new Error('Network error: DNS resolution failed'));

    await expect(stripeRequest('customers', 'POST', { email: 'test@test.com' }, 'sk_test'))
      .rejects.toThrow('Network error');
  });

  it('fetchがタイムアウト: エラーが伝播', async () => {
    globalThis.fetch.mockRejectedValueOnce(new Error('The operation was aborted'));

    await expect(stripeRequest('customers', 'GET', null, 'sk_test'))
      .rejects.toThrow('aborted');
  });

  it('nullやundefinedの値はフォームボディから除外', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'cus_123' }),
    });

    await stripeRequest('customers', 'POST', {
      email: 'test@test.com',
      name: null,
      phone: undefined,
      address: 'Tokyo',
    }, 'sk_test');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toContain('email=test%40test.com');
    expect(options.body).toContain('address=Tokyo');
    // nullやundefinedは含まれない
    expect(options.body).not.toContain('name=');
    expect(options.body).not.toContain('phone=');
  });

  it('空オブジェクトのbody: 空文字列のbody', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'result' }),
    });

    await stripeRequest('endpoint', 'POST', {}, 'sk_test');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toBe('');
  });

  it('数値の値がString変換される', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'result' }),
    });

    await stripeRequest('endpoint', 'POST', { amount: 1500, quantity: 1 }, 'sk_test');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toContain('amount=1500');
    expect(options.body).toContain('quantity=1');
  });
});
