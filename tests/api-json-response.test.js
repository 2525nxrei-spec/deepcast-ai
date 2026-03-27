/**
 * 全APIエンドポイントがJSON形式で応答することをテスト
 * HTMLや502/500プレーンテキストが返らないことを確認
 */

import { describe, it, expect } from 'vitest';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

// 全APIハンドラのインポート
import { onRequestPost as loginHandler } from '../functions/api/auth/login.js';
import { onRequestPost as registerHandler } from '../functions/api/auth/register.js';
import { onRequestGet as meHandler } from '../functions/api/auth/me.js';
import { onRequestPost as checkoutHandler } from '../functions/api/stripe/checkout.js';
import { onRequestGet as stripeKeyHandler } from '../functions/api/stripe/stripe-key.js';
import { onRequestGet as billingStatusHandler } from '../functions/api/billing/status.js';
import { onRequestGet as audioHandler } from '../functions/api/audio/[episode].js';

// JWT生成ヘルパー
async function createTestJWT(payload, secret) {
  const { createJWT } = await import('../functions/lib/crypto.js');
  return createJWT(payload, secret);
}

describe('全APIエンドポイントがJSON形式で応答する', () => {
  it('POST /api/auth/login — 不正リクエストでもJSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {});
    const response = await loginHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('POST /api/auth/register — 不正リクエストでもJSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {});
    const response = await registerHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('GET /api/auth/me — 未認証でもJSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me');
    const response = await meHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('POST /api/stripe/checkout — 未認証でもJSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout');
    const response = await checkoutHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('GET /api/stripe/stripe-key — JSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/stripe/stripe-key');
    const response = await stripeKeyHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('GET /api/billing/status — 未認証でもJSONが返る', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/billing/status');
    const response = await billingStatusHandler({ request, env });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
  });

  it('GET /api/audio/[episode] — Proエピソード未認証で401 JSONが返る', async () => {
    const env = createMockEnv();
    env.AUDIO_BUCKET = {
      get: async () => ({ body: new ReadableStream(), size: 1024 }),
    };
    const request = createRequest('GET', 'https://deepcast-ai.com/api/audio/ep010');
    const response = await audioHandler({ request, env, params: { episode: 'ep010' } });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    const data = await parseResponse(response);
    expect(typeof data).toBe('object');
    expect(data.ok).toBe(false);
  });

  it('GET /api/audio/[episode] — AUDIO_BUCKET未設定で500 JSONが返る', async () => {
    const env = createMockEnv();
    // AUDIO_BUCKETなし
    const request = createRequest('GET', 'https://deepcast-ai.com/api/audio/ep001');
    const response = await audioHandler({ request, env, params: { episode: 'ep001' } });

    expect(response.headers.get('Content-Type')).toContain('application/json');
    expect(response.status).toBe(500);
    const data = await parseResponse(response);
    expect(data.ok).toBe(false);
  });
});
