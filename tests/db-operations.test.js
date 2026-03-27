/**
 * DB操作（モック）の統合テスト
 * ユーザー登録 → ログイン → プラン変更 → 削除のフローを検証
 */
import { describe, it, expect } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('DB操作 — ユーザーライフサイクル統合テスト', () => {
  it('登録 → ログイン → 情報取得 → 削除 の完全フロー', async () => {
    const env = createMockEnv();

    // 1. 登録
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'lifecycle@example.com',
        password: 'password123',
        display_name: 'ライフサイクルテスト',
      }),
      env,
    });
    expect(regRes.status).toBe(201);
    const regJson = await parseResponse(regRes);
    expect(regJson.user.id).toBeDefined();

    // 2. ログイン
    const loginRes = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'lifecycle@example.com',
        password: 'password123',
      }),
      env,
    });
    expect(loginRes.status).toBe(200);
    const loginJson = await parseResponse(loginRes);
    const token = loginJson.token;

    // 3. ユーザー情報取得
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(meRes.status).toBe(200);
    const meJson = await parseResponse(meRes);
    expect(meJson.user.email).toBe('lifecycle@example.com');
    expect(meJson.user.display_name).toBe('ライフサイクルテスト');
    expect(meJson.user.plan).toBe('free');

    // 4. アカウント削除
    const delRes = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'password123',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(delRes.status).toBe(200);

    // 5. 削除後はログインできない
    const loginAfterDelete = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'lifecycle@example.com',
        password: 'password123',
      }),
      env,
    });
    expect(loginAfterDelete.status).toBe(401);
  });

  it('複数ユーザーの同時登録', async () => {
    const env = createMockEnv();

    const users = [
      { email: 'user1@example.com', password: 'password123' },
      { email: 'user2@example.com', password: 'password456' },
      { email: 'user3@example.com', password: 'password789' },
    ];

    const results = await Promise.all(
      users.map(u => register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', u),
        env,
      }))
    );

    for (const res of results) {
      expect(res.status).toBe(201);
    }

    // 各ユーザーが独立してログインできる
    for (const u of users) {
      const loginRes = await login({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', u),
        env,
      });
      expect(loginRes.status).toBe(200);
    }
  });
});
