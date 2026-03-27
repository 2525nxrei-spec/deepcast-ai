/**
 * 認可テスト
 * 他ユーザーのリソースへのアクセス制御、
 * プラン別のアクセス制御を検証
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { onRequestPost as register } from '../functions/api/auth/register.js';
import { onRequestGet as me } from '../functions/api/auth/me.js';
import { onRequestPut as changePassword } from '../functions/api/auth/password.js';
import { onRequestDelete as deleteAccount } from '../functions/api/auth/account.js';
import { createJWT } from '../functions/lib/crypto.js';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

const mockStripeRequest = vi.fn();

vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: (...args) => mockStripeRequest(...args),
  verifyStripeSignature: vi.fn(async (payload) => JSON.parse(payload)),
}));

const { onRequestGet: billingStatus } = await import('../functions/api/billing/status.js');
const { onRequestPost: checkout } = await import('../functions/api/stripe/checkout.js');
const { onRequestPost: portal } = await import('../functions/api/stripe/portal.js');

describe('認可テスト', () => {
  let env;
  let userAToken, userBToken;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockStripeRequest.mockImplementation(async (endpoint) => {
      if (endpoint === 'customers') return { id: 'cus_new' };
      if (endpoint === 'checkout/sessions') return { id: 'cs_1', client_secret: 'secret' };
      if (endpoint === 'billing_portal/sessions') return { url: 'https://billing.stripe.com/p' };
      if (endpoint.startsWith('subscriptions/')) return {
        id: 'sub_1', status: 'active', current_period_end: 1700000000, cancel_at_period_end: false,
      };
      throw new Error('Unknown: ' + endpoint);
    });

    env = createMockEnv();

    // ユーザーA登録
    const resA = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'usera@example.com',
        password: 'password123',
      }),
      env,
    });
    userAToken = (await parseResponse(resA)).token;

    // ユーザーB登録
    const resB = await register({
      request: createRequest('POST', 'https://deepcast-ai.com/api/auth/register', {
        email: 'userb@example.com',
        password: 'password456',
      }),
      env,
    });
    userBToken = (await parseResponse(resB)).token;
  });

  describe('meエンドポイント', () => {
    it('ユーザーAのトークンでAの情報のみ取得', async () => {
      const res = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${userAToken}`,
        }),
        env,
      });
      const json = await parseResponse(res);
      expect(json.user.email).toBe('usera@example.com');
      expect(json.user.email).not.toBe('userb@example.com');
    });

    it('ユーザーBのトークンでBの情報のみ取得', async () => {
      const res = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${userBToken}`,
        }),
        env,
      });
      const json = await parseResponse(res);
      expect(json.user.email).toBe('userb@example.com');
    });
  });

  describe('パスワード変更の認可', () => {
    it('ユーザーAのトークンではユーザーAのパスワードのみ変更可能', async () => {
      const res = await changePassword({
        request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
          current_password: 'password123',
          new_password: 'newpass123',
        }, { Authorization: `Bearer ${userAToken}` }),
        env,
      });
      expect(res.status).toBe(200);
    });

    it('ユーザーAのトークンでBのパスワードは変更不可（自分のパスワードが照合される）', async () => {
      // ユーザーAのトークンでBのパスワードを入れても、Aの現パスワードと照合される
      const res = await changePassword({
        request: createRequest('PUT', 'https://deepcast-ai.com/api/auth/password', {
          current_password: 'password456',  // Bのパスワード
          new_password: 'hacked123',
        }, { Authorization: `Bearer ${userAToken}` }),
        env,
      });
      expect(res.status).toBe(401);
    });
  });

  describe('アカウント削除の認可', () => {
    it('ユーザーBのトークンでBのアカウント削除: 成功', async () => {
      const res = await deleteAccount({
        request: createRequest('DELETE', 'https://deepcast-ai.com/api/auth/account', {
          password: 'password456',
        }, { Authorization: `Bearer ${userBToken}` }),
        env,
      });
      expect(res.status).toBe(200);

      // Bは削除済み、Aはまだ存在
      const resA = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${userAToken}`,
        }),
        env,
      });
      expect(resA.status).toBe(200);
    });
  });

  describe('Billingステータスの分離', () => {
    it('ユーザーAのbillingはAのplan情報のみ', async () => {
      const res = await billingStatus({
        request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
          Authorization: `Bearer ${userAToken}`,
        }),
        env,
      });
      const json = await parseResponse(res);
      expect(json.plan).toBe('free');
    });
  });

  describe('改竄されたJWT', () => {
    it('別のシークレットで署名されたJWT: 401', async () => {
      const fakeToken = await createJWT(
        { sub: 'user-a-id', email: 'usera@example.com', plan: 'pro', exp: Math.floor(Date.now() / 1000) + 3600 },
        'different-secret-key'
      );

      const res = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${fakeToken}`,
        }),
        env,
      });
      expect(res.status).toBe(401);
    });

    it('payloadのplanを改竄してもDBの値が返される', async () => {
      // ユーザーのIDを取得
      const meRes = await me({
        request: createRequest('GET', 'https://deepcast-ai.com/api/auth/me', null, {
          Authorization: `Bearer ${userAToken}`,
        }),
        env,
      });
      const meJson = await parseResponse(meRes);
      const userId = meJson.user.id;

      // proと偽装したJWTを作成（正しいシークレットで）
      const tamperedToken = await createJWT(
        { sub: userId, email: 'usera@example.com', plan: 'pro', exp: Math.floor(Date.now() / 1000) + 3600 },
        env.JWT_SECRET
      );

      // billingでplanを確認 → DBから取得するのでfreeのまま
      const billingRes = await billingStatus({
        request: createRequest('GET', 'https://deepcast-ai.com/api/billing/status', null, {
          Authorization: `Bearer ${tamperedToken}`,
        }),
        env,
      });
      const billingJson = await parseResponse(billingRes);
      expect(billingJson.plan).toBe('free');
    });
  });
});
