/**
 * DELETE /api/auth/account のテスト
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('DELETE /api/auth/account', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'delete-test@example.com',
        password: 'password123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('正常にアカウント削除', async () => {
    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'password123',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.message).toContain('削除');
  });

  it('パスワード不一致: 401', async () => {
    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'wrongpassword',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('パスワードなし: 400', async () => {
    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {}, {
        Authorization: `Bearer ${validToken}`,
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('認証なし: 401', async () => {
    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});
