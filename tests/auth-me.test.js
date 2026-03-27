/**
 * GET /api/auth/me のテスト
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('GET /api/auth/me', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'me-test@example.com',
        password: 'password123',
        display_name: '自分テスト',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('有効なトークンでユーザー情報取得', async () => {
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.user.email).toBe('me-test@example.com');
    expect(json.user.display_name).toBe('自分テスト');
    expect(json.user.plan).toBe('free');
  });

  it('トークンなし: 401', async () => {
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me'),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('不正なトークン: 401', async () => {
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer invalid-token-string',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('Bearer以外のスキーム: 401', async () => {
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Basic ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});
