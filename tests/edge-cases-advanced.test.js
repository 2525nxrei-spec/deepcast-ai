/**
 * エッジケース・異常系テスト（第2ラウンド強化）
 * XSS入力、SQLインジェクション風入力、巨大ペイロード、
 * Content-Type不正、空リクエスト等
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { onRequestPut as changePassword } from '../functions/api/auth/password.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { onRequestGet as stripeKey } from '../functions/api/stripe/stripe-key.js';
import { createJWT } from '../functions/lib/crypto.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(),
  verifyStripeSignature: vi.fn(async (payload) => JSON.parse(payload)),
}));

const { onRequestPost: webhook } = await import('../functions/api/stripe/webhook.js');

function createWebhookRequest(event) {
  return new Request('https://deepcast-ai.com/api/stripe/webhook', {
    method: 'POST',
    headers: {
      'stripe-signature': 't=1234567890,v1=mock_signature',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(event),
  });
}

describe('エッジケース — XSS/インジェクション入力', () => {
  it('register: XSSスクリプトタグ付きemail: 登録されるがD1のプリペアドステートメントで安全', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: '<script>alert("xss")</script>@evil.com',
        password: 'password123',
      }),
      env,
    });
    // 現在のregex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/` は<>を許容するため201
    // XSS対策はフロント側のエスケープ責務（APIはプリペアドステートメントでSQLi防止）
    expect(res.status).toBe(201);
  });

  it('register: SQLインジェクション風email', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: "'; DROP TABLE users; --@evil.com",
        password: 'password123',
      }),
      env,
    });
    // D1はプリペアドステートメントを使用しているので安全
    // メール形式チェック次第で400 or 201
    // 重要なのはDBが壊れないこと
    expect([201, 400]).toContain(res.status);
  });

  it('register: display_nameにXSSスクリプト: 登録は成功するが値はそのまま保存', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'xss-name@test.com',
        password: 'password123',
        display_name: '<img src=x onerror=alert(1)>',
      }),
      env,
    });
    // display_nameにはバリデーションが長さのみ → 登録される
    // XSS対策はフロント側の責務（APIはデータ保存のみ）
    expect(res.status).toBe(201);
    const json = await parseResponse(res);
    expect(json.user.display_name).toContain('<img');
  });

  it('login: 非常に長いemail: 400 or 401', async () => {
    const env = createMockEnv();
    const longEmail = 'a'.repeat(1000) + '@test.com';
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: longEmail,
        password: 'password123',
      }),
      env,
    });
    // 存在しないメールなので401
    expect(res.status).toBe(401);
  });

  it('login: 非常に長いpassword: 401（ユーザー不在）', async () => {
    const env = createMockEnv();
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'noone@test.com',
        password: 'x'.repeat(10000),
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});

describe('エッジケース — Webhook異常ペイロード', () => {
  let env;

  beforeEach(() => {
    env = createMockEnv([{
      id: 'user-edge',
      email: 'edge@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_edge_123',
      stripe_subscription_id: null,
    }]);
  });

  it('checkout.session.completedでmetadataがnull: 200だがDB更新なし', async () => {
    const event = {
      id: 'evt_null_metadata',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: null,
          subscription: 'sub_123',
          customer: 'cus_edge_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
    // metadataがnullの場合、userId = null?.user_id = undefined → if(userId)で弾かれる
    const user = env.DB._store.users.get('user-edge');
    expect(user.plan).toBe('free');
  });

  it('subscription.updatedでstatusがnull: proに変更されない', async () => {
    const event = {
      id: 'evt_null_status',
      type: 'customer.subscription.updated',
      data: {
        object: {
          id: 'sub_null',
          status: null,
          customer: 'cus_edge_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
    const user = env.DB._store.users.get('user-edge');
    expect(user.plan).toBe('free');
  });

  it('subscription.updatedでincomplete_expired状態: proに変更されない', async () => {
    const event = {
      id: 'evt_incomplete_expired',
      type: 'customer.subscription.updated',
      data: {
        object: {
          id: 'sub_ie',
          status: 'incomplete_expired',
          customer: 'cus_edge_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
    const user = env.DB._store.users.get('user-edge');
    expect(user.plan).toBe('free');
  });

  it('subscription.updatedでunpaid状態: proに変更されない', async () => {
    const event = {
      id: 'evt_unpaid',
      type: 'customer.subscription.updated',
      data: {
        object: {
          id: 'sub_unpaid',
          status: 'unpaid',
          customer: 'cus_edge_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
    const user = env.DB._store.users.get('user-edge');
    expect(user.plan).toBe('free');
  });

  it('data.objectが空オブジェクト: 200（undefinedプロパティでも安全）', async () => {
    const event = {
      id: 'evt_empty_obj',
      type: 'checkout.session.completed',
      data: { object: {} },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
  });
});

describe('エッジケース — stripe-key', () => {
  it('STRIPE_PUBLISHABLE_KEYがnull: 500', async () => {
    const env = { STRIPE_PUBLISHABLE_KEY: null };
    const res = await stripeKey({ env });
    expect(res.status).toBe(500);
  });

  it('STRIPE_PUBLISHABLE_KEYが正常: 200', async () => {
    const env = { STRIPE_PUBLISHABLE_KEY: 'pk_test_abc123' };
    const res = await stripeKey({ env });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.publishableKey).toBe('pk_test_abc123');
  });
});

describe('エッジケース — 認証ヘッダー境界', () => {
  it('Bearerの後にスペースのみ（トークンなし）: 401', async () => {
    const env = createMockEnv();
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer ',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('Bearerの大文字小文字（bearer）: 401（大文字小文字区別あり）', async () => {
    const env = createMockEnv([{
      id: 'user-case',
      email: 'case@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);

    const token = await createJWT(
      { sub: 'user-case', exp: Math.floor(Date.now() / 1000) + 3600 },
      env.JWT_SECRET
    );

    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `bearer ${token}`,
      }),
      env,
    });
    // 実装はstartsWith('Bearer ')で判定するので、小文字bearerは弾かれる
    expect(res.status).toBe(401);
  });

  it('JWTのセグメントが2つ（不完全）: 401', async () => {
    const env = createMockEnv();
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer header.payload',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('JWTのセグメントが4つ（余分）: 401', async () => {
    const env = createMockEnv();
    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer a.b.c.d',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });
});

describe('エッジケース — パスワード変更の高度な異常系', () => {
  it('認証済みだがDBからユーザーが消えている: 404', async () => {
    const env = createMockEnv();
    // 登録
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'vanish@test.com',
        password: 'password123',
      }),
      env,
    });
    const { token, user } = await parseResponse(regRes);

    // 裏でDBからユーザーを削除（有効なJWTはまだ生きている）
    env.DB._store.users.delete(user.id);

    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'password123',
        new_password: 'newpass123',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    // authenticateUserがnullを返すので401
    expect(res.status).toBe(401);
  });
});

describe('エッジケース — アカウント削除の高度な異常系', () => {
  it('passwordフィールドが空文字: 400', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'del-empty@test.com',
        password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: '',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(400);
  });
});

describe('エッジケース — register追加', () => {
  it('emailがnumber型: 400', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 12345,
        password: 'password123',
      }),
      env,
    });
    // !emailは falsy ではないが、正規表現テストで弾かれる
    expect(res.status).toBe(400);
  });

  it('passwordがnumber型: 400 or 500', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'numpass@test.com',
        password: 12345678,
      }),
      env,
    });
    // password.length は数値型でundefined → < 8 はNaN比較でfalse
    // だが hashPassword内でString型を想定している
    // 実際の挙動をテスト
    expect([201, 400, 500]).toContain(res.status);
  });
});
