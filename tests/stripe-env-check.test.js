/**
 * Stripe APIキー未設定時のエラーレスポンステスト
 * - STRIPE_SECRET_KEY未設定時に500 JSONが返ること
 * - 502 Bad Gatewayにならないことを確認
 */

import { describe, it, expect } from 'vitest';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';
import { onRequestPost as checkoutHandler } from '../functions/api/stripe/checkout.js';
import { onRequestPost as portalHandler } from '../functions/api/stripe/portal.js';

// JWT生成ヘルパー
async function createTestJWT(payload, secret) {
  const { createJWT } = await import('../functions/lib/crypto.js');
  return createJWT(payload, secret);
}

describe('Stripe APIキー未設定時のエラーレスポンス', () => {
  it('checkout: STRIPE_SECRET_KEY未設定で500 JSONが返る（502にならない）', async () => {
    const env = createMockEnv([
      { id: 'user-1', email: 'test@test.com', plan: 'free', password_hash: 'h', password_salt: 's' },
    ]);
    // STRIPE_SECRET_KEYを削除
    delete env.STRIPE_SECRET_KEY;

    const token = await createTestJWT(
      { sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 },
      env.JWT_SECRET
    );

    const request = createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
      'Authorization': `Bearer ${token}`,
    });

    const response = await checkoutHandler({ request, env });
    const data = await parseResponse(response);

    expect(response.status).toBe(500);
    expect(response.status).not.toBe(502);
    expect(data.ok).toBe(false);
    expect(data.error).toBeTruthy();
    // レスポンスがJSON形式であることを確認
    expect(response.headers.get('Content-Type')).toContain('application/json');
  });

  it('portal: STRIPE_SECRET_KEY未設定で500 JSONが返る', async () => {
    const env = createMockEnv([
      { id: 'user-1', email: 'test@test.com', plan: 'pro', password_hash: 'h', password_salt: 's',
        stripe_customer_id: 'cus_test' },
    ]);
    delete env.STRIPE_SECRET_KEY;

    const token = await createTestJWT(
      { sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 },
      env.JWT_SECRET
    );

    const request = createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
      'Authorization': `Bearer ${token}`,
    });

    const response = await portalHandler({ request, env });
    const data = await parseResponse(response);

    expect(response.status).toBe(500);
    expect(data.ok).toBe(false);
    expect(response.headers.get('Content-Type')).toContain('application/json');
  });
});
