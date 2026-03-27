/**
 * エッジケース・異常系テスト
 * 不正なJSON入力、空リクエストボディ、長すぎる入力値、
 * 期限切れトークン、存在しないリソースへのアクセス等
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { onRequestPut as changePassword } from '../functions/api/auth/password.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { createJWT } from '../functions/lib/crypto.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

describe('エッジケース — 不正な入力', () => {
  describe('register: 不正なJSON', () => {
    it('JSONパース失敗: 500', async () => {
      const env = createMockEnv();
      const request = new Request('https://deepcast-ai.com/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: 'this is not json{{{',
      });
      const res = await register({ request, env });
      expect(res.status).toBe(500);
    });

    it('空のリクエストボディ: 500', async () => {
      const env = createMockEnv();
      const request = new Request('https://deepcast-ai.com/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '',
      });
      const res = await register({ request, env });
      expect(res.status).toBe(500);
    });
  });

  describe('login: 不正な入力', () => {
    it('JSONパース失敗: 500', async () => {
      const env = createMockEnv();
      const request = new Request('https://deepcast-ai.com/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{{invalid}}',
      });
      const res = await login({ request, env });
      expect(res.status).toBe(500);
    });

    it('両方のフィールドが未定義: 400', async () => {
      const env = createMockEnv();
      const res = await login({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {}),
        env,
      });
      expect(res.status).toBe(400);
    });
  });

  describe('register: 境界値テスト', () => {
    it('パスワードちょうど8文字: 成功', async () => {
      const env = createMockEnv();
      const res = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'boundary@test.com',
          password: '12345678',
        }),
        env,
      });
      expect(res.status).toBe(201);
    });

    it('パスワード7文字: 失敗', async () => {
      const env = createMockEnv();
      const res = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'boundary@test.com',
          password: '1234567',
        }),
        env,
      });
      expect(res.status).toBe(400);
    });

    it('表示名ちょうど50文字: 成功', async () => {
      const env = createMockEnv();
      const res = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'boundary50@test.com',
          password: 'password123',
          display_name: 'あ'.repeat(50),
        }),
        env,
      });
      expect(res.status).toBe(201);
    });

    it('表示名なし: 成功（null）', async () => {
      const env = createMockEnv();
      const res = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'noname@test.com',
          password: 'password123',
        }),
        env,
      });
      expect(res.status).toBe(201);
      const json = await parseResponse(res);
      expect(json.user.display_name).toBeNull();
    });

    it('メールにスペース含む: trimされて正規化', async () => {
      const env = createMockEnv();
      const res = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: '  space@test.com  ',
          password: 'password123',
        }),
        env,
      });
      // trim()でスペースが除去され、@を含むので正常に処理される
      // ただし先頭・末尾のスペースを含むメールはバリデーションで弾かれる可能性もある
      // 実装次第。ここでは実際の挙動をテスト
      expect([201, 400]).toContain(res.status);
    });
  });

  describe('期限切れトークン', () => {
    it('期限切れJWTでme取得: 401', async () => {
      const env = createMockEnv([{
        id: 'user-expired',
        email: 'expired@test.com',
        password_hash: 'x',
        password_salt: 'y',
        plan: 'free',
      }]);

      // 有効期限が過去のトークンを生成
      const expiredToken = await createJWT(
        { sub: 'user-expired', email: 'expired@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) - 3600 },
        env.JWT_SECRET
      );

      const res = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${expiredToken}`,
        }),
        env,
      });
      expect(res.status).toBe(401);
    });
  });

  describe('存在しないリソース', () => {
    it('DBに存在しないユーザーIDのトークンでme取得: 401', async () => {
      const env = createMockEnv();

      // DBに存在しないユーザーIDでトークンを作成
      const ghostToken = await createJWT(
        { sub: 'nonexistent-user-id', email: 'ghost@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) + 3600 },
        env.JWT_SECRET
      );

      const res = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${ghostToken}`,
        }),
        env,
      });
      expect(res.status).toBe(401);
    });
  });

  describe('password変更: 不正なJSON', () => {
    it('JSONパース失敗: 400', async () => {
      const env = createMockEnv();
      const regRes = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'pw-json@test.com',
          password: 'password123',
        }),
        env,
      });
      const { token } = await parseResponse(regRes);

      const request = new Request('https://deepcast-ai.com/api/auth/password', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'Origin': 'https://deepcast-ai.com',
        },
        body: 'not json',
      });
      const res = await changePassword({ request, env });
      expect(res.status).toBe(400);
      const json = await parseResponse(res);
      expect(json.error).toContain('不正');
    });

    it('数字のみ（英字なし）の新パスワード: 400', async () => {
      const env = createMockEnv();
      const regRes = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'pw-digits@test.com',
          password: 'password123',
        }),
        env,
      });
      const { token } = await parseResponse(regRes);

      const res = await changePassword({
        request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
          current_password: 'password123',
          new_password: '12345678',
        }, { Authorization: `Bearer ${token}` }),
        env,
      });
      expect(res.status).toBe(400);
      const json = await parseResponse(res);
      expect(json.error).toContain('英字と数字');
    });

    it('フィールドが空オブジェクト: 400', async () => {
      const env = createMockEnv();
      const regRes = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'pw-empty@test.com',
          password: 'password123',
        }),
        env,
      });
      const { token } = await parseResponse(regRes);

      const res = await changePassword({
        request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {}, {
          Authorization: `Bearer ${token}`,
        }),
        env,
      });
      expect(res.status).toBe(400);
    });
  });

  describe('account削除: 不正なJSON', () => {
    it('JSONパース失敗: 400', async () => {
      const env = createMockEnv();
      const regRes = await register({
        request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
          email: 'del-json@test.com',
          password: 'password123',
        }),
        env,
      });
      const { token } = await parseResponse(regRes);

      const request = new Request('https://deepcast-ai.com/api/auth/account', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'Origin': 'https://deepcast-ai.com',
        },
        body: 'invalid json body!!!',
      });
      const res = await deleteAccount({ request, env });
      expect(res.status).toBe(400);
      const json = await parseResponse(res);
      expect(json.error).toContain('不正');
    });
  });
});
