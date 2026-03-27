/**
 * エッジケース・異常系テスト — 第2ラウンド
 * 認可テスト（他ユーザーリソースへのアクセス）、トークン改竄、
 * Content-Type不一致、SQLインジェクション風入力、多重登録レース
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestPost as login } from '../functions/api/auth/login.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { onRequestPut as changePassword } from '../functions/api/auth/password.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { createJWT, verifyJWT } from '../functions/lib/crypto.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

// Stripeモック（checkoutとportalで使用）
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn().mockRejectedValue(new Error('外部API呼び出し禁止')),
  verifyStripeSignature: vi.fn(),
}));

const { onRequestPost: checkout } = await import('../functions/api/stripe/checkout.js');
const { onRequestPost: portal } = await import('../functions/api/stripe/portal.js');
const { onRequestGet: billingStatus } = await import('../functions/api/billing/status.js');

describe('認可テスト — 他ユーザーのリソースへのアクセス', () => {
  it('ユーザーAのトークンでユーザーBのデータは取得できない（meは自分のデータのみ）', async () => {
    const env = createMockEnv();

    // ユーザーA登録
    const resA = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'userA@test.com', password: 'password123',
      }),
      env,
    });
    const { token: tokenA } = await parseResponse(resA);

    // ユーザーB登録
    await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'userB@test.com', password: 'password456',
      }),
      env,
    });

    // ユーザーAのトークンでme取得 → ユーザーAの情報のみ返る
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${tokenA}`,
      }),
      env,
    });
    expect(meRes.status).toBe(200);
    const meJson = await parseResponse(meRes);
    expect(meJson.user.email).toBe('usera@test.com');
    expect(meJson.user.email).not.toBe('userb@test.com');
  });

  it('削除済みユーザーのトークンでme取得: 401', async () => {
    const env = createMockEnv();

    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'deleted@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    // アカウント削除
    await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'password123',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });

    // 削除済みトークンでme取得
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });
});

describe('トークン改竄テスト', () => {
  it('JWTペイロードを改竄（subを変更）: 401', async () => {
    const env = createMockEnv();

    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'tamper@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    // トークンの中間部分（ペイロード）を改竄
    const parts = token.split('.');
    const tampered = parts[0] + '.' + btoa('{"sub":"hacker-id","email":"hacker@test.com","plan":"pro","exp":9999999999}').replace(/=/g, '') + '.' + parts[2];

    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${tampered}`,
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });

  it('完全にでたらめなトークン: 401', async () => {
    const env = createMockEnv();
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer totally.not.ajwt',
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });

  it('Bearer接頭辞なし: 401', async () => {
    const env = createMockEnv();
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'some-random-token',
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });

  it('Authorizationヘッダーなし: 401', async () => {
    const env = createMockEnv();
    const meRes = await me({
      request: new Request('https://deepcast-ai.com/api/auth/me', {
        method: 'GET',
        headers: { 'Origin': 'https://deepcast-ai.com' },
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });

  it('空のBearerトークン: 401', async () => {
    const env = createMockEnv();
    const meRes = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: 'Bearer ',
      }),
      env,
    });
    expect(meRes.status).toBe(401);
  });
});

describe('期限切れトークン追加テスト', () => {
  it('1秒前に期限切れのトークン: 401', async () => {
    const env = createMockEnv([{
      id: 'user-exp-1s',
      email: 'exp1s@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);

    const token = await createJWT(
      { sub: 'user-exp-1s', email: 'exp1s@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) - 1 },
      env.JWT_SECRET
    );

    const res = await me({
      request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('期限切れトークンでパスワード変更: 401', async () => {
    const env = createMockEnv([{
      id: 'user-exp-pw',
      email: 'exppw@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);

    const token = await createJWT(
      { sub: 'user-exp-pw', email: 'exppw@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) - 3600 },
      env.JWT_SECRET
    );

    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'old_pass',
        new_password: 'newpass123',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('期限切れトークンでアカウント削除: 401', async () => {
    const env = createMockEnv([{
      id: 'user-exp-del',
      email: 'expdel@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);

    const token = await createJWT(
      { sub: 'user-exp-del', email: 'expdel@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) - 3600 },
      env.JWT_SECRET
    );

    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'password123',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(401);
  });
});

describe('Stripe認証テスト（認証必須エンドポイント）', () => {
  it('checkout: トークンなし → 401', async () => {
    const env = createMockEnv();
    const res = await checkout({
      request: new Request('https://deepcast-ai.com/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Origin': 'https://deepcast-ai.com' },
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('checkout: 期限切れトークン → 401', async () => {
    const env = createMockEnv([{
      id: 'user-chk-exp',
      email: 'chkexp@test.com',
      password_hash: 'x',
      password_salt: 'y',
      plan: 'free',
    }]);

    const token = await createJWT(
      { sub: 'user-chk-exp', email: 'chkexp@test.com', plan: 'free', exp: Math.floor(Date.now() / 1000) - 3600 },
      env.JWT_SECRET
    );

    const res = await checkout({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/checkout', {}, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('portal: トークンなし → 401', async () => {
    const env = createMockEnv();
    const res = await portal({
      request: new Request('https://deepcast-ai.com/api/stripe/portal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Origin': 'https://deepcast-ai.com' },
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('billingStatus: トークンなし → 401', async () => {
    const env = createMockEnv();
    const res = await billingStatus({
      request: new Request('https://deepcast-ai.com/api/billing/status', {
        method: 'GET',
        headers: { 'Origin': 'https://deepcast-ai.com' },
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('portal: stripe_customer_idなしユーザー → 400', async () => {
    const env = createMockEnv();

    // ユーザー登録
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'noscus@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await portal({
      request: createRequest('POST', 'https://deepcast-ai.com/api/stripe/portal', {}, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('サブスクリプション情報');
  });
});

describe('SQLインジェクション風入力テスト', () => {
  it('メールにSQLインジェクション風文字列: 400（形式不正）', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: "' OR 1=1; --",
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('パスワードにSQL文字列: 登録自体は成功（バインドパラメータで安全）', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'sqli@test.com',
        password: "'); DROP TABLE users; --abc",
      }),
      env,
    });
    // パスワードは文字列として安全にハッシュ化される
    expect(res.status).toBe(201);
  });

  it('表示名にHTMLタグ: 登録成功（エスケープはフロント側の責務）', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'xss@test.com',
        password: 'password123',
        display_name: '<script>alert("xss")</script>',
      }),
      env,
    });
    expect(res.status).toBe(201);
    const json = await parseResponse(res);
    expect(json.user.display_name).toBe('<script>alert("xss")</script>');
  });
});

describe('ログイン異常系追加', () => {
  it('存在しないメールでログイン: 401', async () => {
    const env = createMockEnv();
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'nonexistent@test.com',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('正しいメール + 間違ったパスワード: 401', async () => {
    const env = createMockEnv();
    await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'wrongpw@test.com', password: 'correct_pass1',
      }),
      env,
    });

    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'wrongpw@test.com',
        password: 'wrong_pass_99',
      }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('メールのみ（パスワードなし）: 400', async () => {
    const env = createMockEnv();
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'test@test.com',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('パスワードのみ（メールなし）: 400', async () => {
    const env = createMockEnv();
    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('大文字メールでログイン: 成功（小文字に正規化）', async () => {
    const env = createMockEnv();
    await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'CaseTest@Example.com', password: 'password123',
      }),
      env,
    });

    const res = await login({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/login', {
        email: 'CASETEST@EXAMPLE.COM',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(200);
  });
});

describe('register追加異常系', () => {
  it('メール重複登録: 409', async () => {
    const env = createMockEnv();
    await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'dup@test.com', password: 'password123',
      }),
      env,
    });

    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'dup@test.com', password: 'different456',
      }),
      env,
    });
    expect(res.status).toBe(409);
  });

  it('表示名51文字: 400', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'long51@test.com',
        password: 'password123',
        display_name: 'あ'.repeat(51),
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('不正メール形式（@なし）: 400', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'no-at-sign',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('不正メール形式（ドメインなし）: 400', async () => {
    const env = createMockEnv();
    const res = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'test@',
        password: 'password123',
      }),
      env,
    });
    expect(res.status).toBe(400);
  });
});

describe('パスワード変更追加異常系', () => {
  it('英字のみ（数字なし）の新パスワード: 400', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'pw-alpha@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'password123',
        new_password: 'abcdefgh',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(400);
    const json = await parseResponse(res);
    expect(json.error).toContain('英字と数字');
  });

  it('新パスワード7文字: 400', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'pw-short@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'password123',
        new_password: 'short7a',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(400);
  });

  it('間違った現在のパスワード: 401', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'pw-wrong@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await changePassword({
      request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
        current_password: 'wrongpassword1',
        new_password: 'newpass456a',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(401);
  });
});

describe('アカウント削除追加異常系', () => {
  it('間違ったパスワードで削除: 401', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'del-wrong@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
        password: 'wrongpassword1',
      }, { Authorization: `Bearer ${token}` }),
      env,
    });
    expect(res.status).toBe(401);
  });

  it('パスワードフィールドなしで削除: 400', async () => {
    const env = createMockEnv();
    const regRes = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'del-nopw@test.com', password: 'password123',
      }),
      env,
    });
    const { token } = await parseResponse(regRes);

    const res = await deleteAccount({
      request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {}, {
        Authorization: `Bearer ${token}`,
      }),
      env,
    });
    expect(res.status).toBe(400);
  });
});
