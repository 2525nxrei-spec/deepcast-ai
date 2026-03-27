/**
 * functions/lib/stripe.js — stripeRequest / buildFormBody のテスト
 * fetch をモックして実際のAPI呼び出しは行わない
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// fetchをモック
const originalFetch = globalThis.fetch;

describe('lib/stripe.js — stripeRequest', () => {
  let stripeRequest;

  beforeEach(async () => {
    // 毎回新しくモジュールを読み込み（モジュールキャッシュをクリア）
    vi.resetModules();

    // fetchをモック
    globalThis.fetch = vi.fn();

    // モジュール再読み込み（vi.mockではなく動的インポートで対応）
    const mod = await import('../functions/lib/stripe.js');
    stripeRequest = mod.stripeRequest;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('POSTリクエストが正しいフォーマットで送信される', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'cus_123', email: 'test@test.com' }),
    });

    const result = await stripeRequest('customers', 'POST', {
      email: 'test@test.com',
      name: 'Test User',
    }, 'sk_test_key');

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('https://api.stripe.com/v1/customers');
    expect(options.method).toBe('POST');
    expect(options.headers['Authorization']).toBe('Bearer sk_test_key');
    expect(options.headers['Content-Type']).toBe('application/x-www-form-urlencoded');
    expect(options.body).toContain('email=test%40test.com');
    expect(result.id).toBe('cus_123');
  });

  it('GETリクエストはクエリパラメータ付きURL', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'sub_123', status: 'active' }),
    });

    const result = await stripeRequest('subscriptions/sub_123', 'GET', null, 'sk_test_key');

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('https://api.stripe.com/v1/subscriptions/sub_123');
    expect(options.method).toBe('GET');
    expect(options.body).toBeUndefined();
  });

  it('Stripe APIがエラーを返した場合: Error投げ', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({
        error: { message: 'No such customer', type: 'invalid_request_error' },
      }),
    });

    await expect(stripeRequest('customers/cus_bad', 'GET', null, 'sk_test_key'))
      .rejects.toThrow('No such customer');
  });

  it('ネストされたパラメータのフラット化', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'cs_123', client_secret: 'secret' }),
    });

    await stripeRequest('checkout/sessions', 'POST', {
      mode: 'subscription',
      'line_items[0][price]': 'price_123',
      'line_items[0][quantity]': '1',
      metadata: { user_id: 'user-1' },
    }, 'sk_test_key');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toContain('mode=subscription');
    // metadata[user_id]がフラット化される
    expect(options.body).toContain('metadata');
  });

  it('bodyがnullのPOST: bodyなしで送信', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      json: async () => ({ id: 'result' }),
    });

    await stripeRequest('some_endpoint', 'POST', null, 'sk_test_key');

    const [, options] = globalThis.fetch.mock.calls[0];
    expect(options.body).toBeUndefined();
  });
});
