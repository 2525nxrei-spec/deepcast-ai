/**
 * POST /api/auth/login のテスト
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('POST /api/auth/login', () => {
  let env;

  beforeEach(async () => {
    env = createMockEnv();
    // テストユーザーを事前登録
    await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'login-test@example.com',
        password: 'password123',
        display_name: 'ログインテスト',
      }),
      env,
    });
  });

  it('正常ログイン: 200 + token + user', async () => {
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'login-test@example.com',
        password: 'password123',
      }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.token).toBeDefined();
    expect(json.user.email).toBe('login-test@example.com');
  });

  it('存在しないメール: 401', async () => {
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'nouser@example.com',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('パスワード不一致: 401', async () => {
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'login-test@example.com',
        password: 'wrongpassword',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('メール空: 400', async () => {
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: '',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('パスワード空: 400', async () => {
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'login-test@example.com',
        password: '',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });
});
