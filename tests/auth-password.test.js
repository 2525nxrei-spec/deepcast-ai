/**
 * PUT /api/auth/password のテスト
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestPut as changePassword } from '../functions/api/auth/password.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('PUT /api/auth/password', () => {
  let env;
  let validToken;

  beforeEach(async () => {
    env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'pw-test@example.com',
        password: 'oldpass123',
      }),
      env,
    });
    const json = await parseResponse(res);
    validToken = json.token;
  });

  it('正常にパスワード変更', async () => {
    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'oldpass123',
        new_password: 'newpass456',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });

    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.message).toContain('変更');

    // 新しいパスワードでログインできる
    const loginRes = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'pw-test@example.com',
        password: 'newpass456',
      }),
      env,
    });
    expect(loginRes.status).toBe(200);
  });

  it('現在のパスワードが違う: 401', async () => {
    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'wrongpass',
        new_password: 'newpass456',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('新パスワード8文字未満: 400', async () => {
    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'oldpass123',
        new_password: 'short',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('8文字');
  });

  it('英字のみ（数字なし）: 400', async () => {
    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'oldpass123',
        new_password: 'onlyletters',
      }, { Authorization: `Bearer ${validToken}` }),
      env,
    });
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('英字と数字');
  });

  it('認証なし: 401', async () => {
    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'oldpass123',
        new_password: 'newpass456',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});
