/**
 * functions/lib/auth.js — authenticateUser のテスト
 */
import { describe, it, expect } from 'vitest';
import { authenticateUser } from '../functions/lib/auth.js';
import { createJWT } from '../functions/lib/crypto.js';
import { createMockEnv, createRequest } from './helpers.js';

describe('lib/auth.js — authenticateUser', () => {
  const JWT_SECRET = 'test-jwt-secret-key-for-ci';

  it('正しいトークンでユーザーを返す', async () => {
    const env = createMockEnv([{
      id: 'user-auth-1',
      email: 'auth@test.com',
      display_name: 'Auth User',
      plan: 'free',
      password_hash: 'x',
      password_salt: 'y',
      stripe_customer_id: null,
      stripe_subscription_id: null,
    }]);

    const token = await createJWT(
      { sub: 'user-auth-1', email: 'auth@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) + 3600 },
      JWT_SECRET
    );

    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: `Bearer ${token}`,
    });

    const user = await authenticateUser(request, env);
    expect(user).not.toBeNull();
    expect(user.id).toBe('user-auth-1');
    expect(user.email).toBe('auth@test.com');
  });

  it('Authorizationヘッダーなし: null', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me');
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });

  it('Bearerプレフィックスなし: null', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: 'Token some-token-here',
    });
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });

  it('不正なJWT: null', async () => {
    const env = createMockEnv();
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: 'Bearer not.a.valid.jwt',
    });
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });

  it('subがないJWT: null', async () => {
    const env = createMockEnv();
    // subなしのトークン
    const token = await createJWT(
      { email: 'nosub@test.com', exp: Math.floor(Date.now() / 1000) + 3600 },
      JWT_SECRET
    );
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: `Bearer ${token}`,
    });
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });

  it('期限切れJWT: null', async () => {
    const env = createMockEnv([{
      id: 'user-exp',
      email: 'exp@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);
    const token = await createJWT(
      { sub: 'user-exp', exp: Math.floor(Date.now() / 1000) - 100 },
      JWT_SECRET
    );
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: `Bearer ${token}`,
    });
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });

  it('DBにユーザーが存在しない: null', async () => {
    const env = createMockEnv(); // 空DB
    const token = await createJWT(
      { sub: 'ghost-user', exp: Math.floor(Date.now() / 1000) + 3600 },
      JWT_SECRET
    );
    const request = createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
      Authorization: `Bearer ${token}`,
    });
    const user = await authenticateUser(request, env);
    expect(user).toBeNull();
  });
});
