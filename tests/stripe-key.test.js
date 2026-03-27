/**
 * GET /api/stripe/stripe-key のテスト
 */
import { describe, it, expect } from 'vitest';
import { onRequestGet } from '../functions/api/stripe/stripe-key.js';
import { createMockEnv, parseResponse } from './helpers.js';

describe('GET /api/stripe/stripe-key', () => {
  it('公開鍵を返す', async () => {
    const env = createMockEnv();
    const res = await onRequestGet({ env });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.publishableKey).toBe('pk_test_fake_key');
  });

  it('公開鍵が未設定: 500', async () => {
    const env = createMockEnv();
    env.STRIPE_PUBLISHABLE_KEY = '';
    const res = await onRequestGet({ env });

    expect(res.status).toBe(500);
    const json = await parseResponse(res);
    expect(json.ok).toBe(false);
  });
});
