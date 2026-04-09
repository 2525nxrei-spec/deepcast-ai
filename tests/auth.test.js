/**
 * 認証系テスト — register / login / me
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { createTestEnv, createTestUser, createExpiredToken, createContext, parseResponse } from './helpers.js';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';

let mf, db, env;

beforeAll(async () => {
  ({ mf, db, env } = await createTestEnv());
});

afterAll(async () => {
  await mf.dispose();
});

// テスト間でDBをクリーン
beforeEach(async () => {
  await db.exec('DELETE FROM users');
});

// === POST /api/auth/register ===

describe('POST /api/auth/register', () => {
  it('正常な登録 — 201とJWTが返る', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'new@example.com',
        password: 'Password1',
        display_name: 'テスト太郎',
      }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(201);
    expect(body.ok).toBe(true);
    expect(body.token).toBeTruthy();
    expect(body.user.email).toBe('new@example.com');
    expect(body.user.plan).toBe('free');
    expect(body.user.display_name).toBe('テスト太郎');
  });

  it('メールアドレス重複 — 409を返す', async () => {
    await createTestUser(db, { email: 'dup@example.com' });

    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'dup@example.com', password: 'Password1' }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(409);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('既に登録');
  });

  it('メールアドレス未入力 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: '', password: 'Password1' }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.ok).toBe(false);
  });

  it('パスワードが短すぎる — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'short@example.com', password: 'Ab1' }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.error).toContain('8文字以上');
  });

  it('パスワードに数字がない — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'nonum@example.com', password: 'PasswordOnly' }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.error).toContain('英字と数字');
  });

  it('不正なメール形式 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'not-an-email', password: 'Password1' }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.error).toContain('メールアドレスの形式');
  });

  it('表示名が50文字超 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'longname@example.com',
        password: 'Password1',
        display_name: 'あ'.repeat(51),
      }),
    });

    const res = await register(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.error).toContain('50文字以内');
  });

  it('メールアドレスは小文字に正規化される', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'UpperCase@Example.COM', password: 'Password1' }),
    });

    const res = await register(createContext(request, env));
    const { body } = await parseResponse(res);

    expect(body.user.email).toBe('uppercase@example.com');
  });
});

// === POST /api/auth/login ===

describe('POST /api/auth/login', () => {
  it('正常ログイン — 200とJWTが返る', async () => {
    const user = await createTestUser(db, { email: 'login@example.com', password: 'Password1' });

    const request = new Request('https://deepcast-ai.com/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'login@example.com', password: 'Password1' }),
    });

    const res = await login(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.token).toBeTruthy();
    expect(body.user.email).toBe('login@example.com');
  });

  it('不正なパスワード — 401を返す', async () => {
    await createTestUser(db, { email: 'badpw@example.com', password: 'Password1' });

    const request = new Request('https://deepcast-ai.com/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'badpw@example.com', password: 'WrongPassword1' }),
    });

    const res = await login(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
  });

  it('存在しないメールアドレス — 401を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'nobody@example.com', password: 'Password1' }),
    });

    const res = await login(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
  });

  it('メール・パスワード未入力 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: '', password: '' }),
    });

    const res = await login(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.ok).toBe(false);
  });
});

// === GET /api/auth/me ===

describe('GET /api/auth/me', () => {
  it('有効なJWTでユーザー情報が返る', async () => {
    const user = await createTestUser(db, { email: 'me@example.com' });

    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await me(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(200);
    expect(body.ok).toBe(true);
    expect(body.user.email).toBe('me@example.com');
    expect(body.user.id).toBe(user.id);
  });

  it('無効なJWT — 401を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Authorization': 'Bearer invalid.token.here' },
    });

    const res = await me(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('認証');
  });

  it('期限切れJWT — 401を返す', async () => {
    const user = await createTestUser(db, { email: 'expired@example.com' });
    const expiredToken = await createExpiredToken(user.id, user.email);

    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${expiredToken}` },
    });

    const res = await me(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
  });

  it('Authorizationヘッダーなし — 401を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
    });

    const res = await me(createContext(request, env));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
  });
});
