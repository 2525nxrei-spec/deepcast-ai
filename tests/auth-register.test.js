/**
 * POST /api/auth/register のテスト
 */
import { describe, it, expect } from 'vitest';
import { onRequestPost } from '../functions/api/auth/register.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

function makeContext(body, env) {
  return {
    request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', body),
    env,
  };
}

describe('POST /api/auth/register', () => {
  it('正常登録: 201 + token + user', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({
      email: 'new@example.com',
      password: 'password123',
      display_name: 'テストユーザー',
    }, env));

    expect(res.status).toBe(201);
    const json = await parseResponse(res);
    expect(json.ok).toBe(true);
    expect(json.token).toBeDefined();
    expect(json.user.email).toBe('new@example.com');
    expect(json.user.plan).toBe('free');
    expect(json.user.display_name).toBe('テストユーザー');
  });

  it('メールなし: 400', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({ password: 'pass1234' }, env));
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.ok).toBe(false);
  });

  it('パスワードなし: 400', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({ email: 'a@b.com' }, env));
    expect(res.status).toBe(400);
  });

  it('パスワード8文字未満: 400', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({
      email: 'a@b.com', password: '1234567',
    }, env));
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('8文字');
  });

  it('不正なメール形式: 400', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({
      email: 'invalid-email', password: 'password123',
    }, env));
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('メールアドレスの形式');
  });

  it('表示名51文字以上: 400', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({
      email: 'a@b.com', password: 'password123',
      display_name: 'あ'.repeat(51),
    }, env));
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('50文字');
  });

  it('メール重複: 409', async () => {
    const env = createMockEnv([{
      id: 'existing-user', email: 'dup@example.com',
      password_hash: 'xxx', password_salt: 'yyy', plan: 'free',
    }]);
    const res = await onRequestPost(makeContext({
      email: 'dup@example.com', password: 'password123',
    }, env));
    expect(res.status).toBe(409);
    const json = await parseResponse(res);
    expect(json.error).toContain('既に登録');
  });

  it('メールは小文字に正規化される', async () => {
    const env = createMockEnv();
    const res = await onRequestPost(makeContext({
      email: 'Upper@CASE.Com', password: 'password123',
    }, env));
    expect(res.status).toBe(201);
    const json = await parseResponse(res);
    expect(json.user.email).toBe('upper@case.com');
  });
});
