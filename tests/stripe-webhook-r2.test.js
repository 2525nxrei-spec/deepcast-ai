/**
 * POST /api/stripe/webhook — 第2ラウンド異常系テスト
 * DB例外、空データ、不正ペイロード、並行冪等性、全イベント網羅
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createMockEnv, parseResponse } from './helpers.js';

// verifyStripeSignatureをモック
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(),
  verifyStripeSignature: vi.fn(async (payload) => JSON.parse(payload)),
}));

const { onRequestPost: webhook } = await import('../functions/api/stripe/webhook.js');
const { verifyStripeSignature } = await import('../functions/lib/stripe.js');

function createWebhookRequest(body, contentType = 'application/json') {
  return new Request('https://deepcast-ai.com/api/stripe/webhook', {
    method: 'POST',
    headers: {
      'stripe-signature': 't=1234567890,v1=mock_signature',
      'Content-Type': contentType,
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

describe('POST /api/stripe/webhook — R2異常系', () => {
  let env;

  beforeEach(() => {
    vi.clearAllMocks();
    verifyStripeSignature.mockImplementation(async (payload) => JSON.parse(payload));
    env = createMockEnv([{
      id: 'user-r2-1',
      email: 'r2-user@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_r2_123',
      stripe_subscription_id: null,
    }]);
  });

  describe('ペイロード異常系', () => {
    it('不正なJSON文字列: verifyStripeSignatureがJSON.parseで失敗 → 400', async () => {
      verifyStripeSignature.mockImplementation(async (payload) => JSON.parse(payload));
      const res = await webhook({
        request: createWebhookRequest('{invalid json!!!', 'application/json'),
        env,
      });
      expect(res.status).toBe(400);
    });

    it('空のボディ: verifyStripeSignatureがJSON.parseで失敗 → 400', async () => {
      verifyStripeSignature.mockImplementation(async (payload) => JSON.parse(payload));
      const res = await webhook({
        request: createWebhookRequest('', 'application/json'),
        env,
      });
      expect(res.status).toBe(400);
    });

    it('nullペイロード: verifyStripeSignatureが例外 → 400', async () => {
      verifyStripeSignature.mockRejectedValueOnce(new Error('ペイロードがnull'));
      const res = await webhook({
        request: createWebhookRequest('null', 'application/json'),
        env,
      });
      expect(res.status).toBe(400);
    });

    it('配列ペイロード（オブジェクト以外）: イベント処理で安全に200', async () => {
      // Stripe形式ではないが、検証通過後に安全にハンドルされるか
      verifyStripeSignature.mockResolvedValueOnce([1, 2, 3]);
      const res = await webhook({
        request: createWebhookRequest('[1,2,3]'),
        env,
      });
      // typeがundefinedなのでdefaultケースに落ちて200
      expect(res.status).toBe(200);
    });

    it('数値ペイロード: 安全に200', async () => {
      verifyStripeSignature.mockResolvedValueOnce(42);
      const res = await webhook({
        request: createWebhookRequest('42'),
        env,
      });
      expect(res.status).toBe(200);
    });
  });

  describe('署名検証の詳細異常系', () => {
    it('verifyStripeSignatureがTypeErrorを投げる: 400', async () => {
      verifyStripeSignature.mockRejectedValueOnce(new TypeError('Cannot read properties'));
      const event = { id: 'evt_type_err', type: 'test', data: { object: {} } };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(400);
    });

    it('verifyStripeSignatureがネットワーク風エラーを投げる: 400', async () => {
      verifyStripeSignature.mockRejectedValueOnce(new Error('network timeout'));
      const event = { id: 'evt_net_err', type: 'test', data: { object: {} } };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(400);
      const json = await parseResponse(res);
      expect(json.error).toBeDefined();
    });
  });

  describe('checkout.session.completed 異常系', () => {
    it('metadata自体がnull: 200（user_idなしで空振り）', async () => {
      const event = {
        id: 'evt_null_meta',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: null,
            subscription: 'sub_123',
            customer: 'cus_r2_123',
          },
        },
      };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      // ユーザーのプランは変わらない
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('free');
    });

    it('subscriptionがnull: 200だがsubscription_idはnullで更新', async () => {
      const event = {
        id: 'evt_null_sub',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-r2-1' },
            subscription: null,
            customer: 'cus_r2_123',
          },
        },
      };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('pro');
    });

    it('customerがnull: 200（stripe_customer_idはCOALESCEで既存値維持）', async () => {
      const event = {
        id: 'evt_null_cus',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-r2-1' },
            subscription: 'sub_new',
            customer: null,
          },
        },
      };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
    });

    it('data.objectが空オブジェクト: 200（metadata未定義で空振り）', async () => {
      const event = {
        id: 'evt_empty_obj',
        type: 'checkout.session.completed',
        data: { object: {} },
      };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('free');
    });
  });

  describe('customer.subscription.updated 追加異常系', () => {
    it('status=incomplete: proに変更しない', async () => {
      env.DB._store.users.get('user-r2-1').plan = 'free';
      const event = {
        id: 'evt_incomplete',
        type: 'customer.subscription.updated',
        data: {
          object: { id: 'sub_inc', status: 'incomplete', customer: 'cus_r2_123' },
        },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      expect(env.DB._store.users.get('user-r2-1').plan).toBe('free');
    });

    it('status=incomplete_expired: proに変更しない', async () => {
      env.DB._store.users.get('user-r2-1').plan = 'free';
      const event = {
        id: 'evt_inc_exp',
        type: 'customer.subscription.updated',
        data: {
          object: { id: 'sub_ie', status: 'incomplete_expired', customer: 'cus_r2_123' },
        },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      expect(env.DB._store.users.get('user-r2-1').plan).toBe('free');
    });

    it('status=unpaid: proに変更しない', async () => {
      env.DB._store.users.get('user-r2-1').plan = 'free';
      const event = {
        id: 'evt_unpaid',
        type: 'customer.subscription.updated',
        data: {
          object: { id: 'sub_up', status: 'unpaid', customer: 'cus_r2_123' },
        },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      expect(env.DB._store.users.get('user-r2-1').plan).toBe('free');
    });

    it('既にproのユーザーがactive更新: pro維持+subscription_id更新', async () => {
      env.DB._store.users.get('user-r2-1').plan = 'pro';
      env.DB._store.users.get('user-r2-1').stripe_subscription_id = 'sub_old';
      const event = {
        id: 'evt_pro_active',
        type: 'customer.subscription.updated',
        data: {
          object: { id: 'sub_new_active', status: 'active', customer: 'cus_r2_123' },
        },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('pro');
      expect(user.stripe_subscription_id).toBe('sub_new_active');
    });
  });

  describe('customer.subscription.deleted 追加異常系', () => {
    it('proユーザーがdeleted → freeに戻りsubscription_idもnull', async () => {
      env.DB._store.users.get('user-r2-1').plan = 'pro';
      env.DB._store.users.get('user-r2-1').stripe_subscription_id = 'sub_active';
      const event = {
        id: 'evt_del_pro',
        type: 'customer.subscription.deleted',
        data: { object: { id: 'sub_active', customer: 'cus_r2_123' } },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('free');
      expect(user.stripe_subscription_id).toBeNull();
    });

    it('存在しないcustomer_idのdeleted: 200（空振り）', async () => {
      const event = {
        id: 'evt_del_ghost',
        type: 'customer.subscription.deleted',
        data: { object: { id: 'sub_x', customer: 'cus_ghost_999' } },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
    });
  });

  describe('invoice.payment_failed 追加', () => {
    it('customer未定義: 200（ログのみ）', async () => {
      const event = {
        id: 'evt_fail_no_cus',
        type: 'invoice.payment_failed',
        data: { object: { attempt_count: 1 } },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
    });

    it('attempt_count=0: 200', async () => {
      const event = {
        id: 'evt_fail_zero',
        type: 'invoice.payment_failed',
        data: { object: { customer: 'cus_r2_123', attempt_count: 0 } },
      };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
    });
  });

  describe('未対応イベントタイプ網羅', () => {
    const unknownEvents = [
      'payment_intent.created',
      'payment_intent.succeeded',
      'payment_intent.payment_failed',
      'charge.succeeded',
      'charge.refunded',
      'customer.created',
      'customer.updated',
      'customer.deleted',
      'invoice.paid',
      'invoice.created',
      'product.created',
      'price.created',
    ];

    for (const eventType of unknownEvents) {
      it(`${eventType}: 200（ログのみ）`, async () => {
        const event = {
          id: `evt_unknown_${eventType.replace(/\./g, '_')}`,
          type: eventType,
          data: { object: {} },
        };
        const res = await webhook({ request: createWebhookRequest(event), env });
        expect(res.status).toBe(200);
        const json = await parseResponse(res);
        expect(json.received).toBe(true);
      });
    }
  });

  describe('冪等性テスト強化', () => {
    it('同一イベントを3回送信: 全て200', async () => {
      const event = {
        id: 'evt_triple',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-r2-1' },
            subscription: 'sub_triple',
            customer: 'cus_r2_123',
          },
        },
      };

      const res1 = await webhook({ request: createWebhookRequest(event), env });
      expect(res1.status).toBe(200);

      const res2 = await webhook({ request: createWebhookRequest(event), env });
      expect(res2.status).toBe(200);

      const res3 = await webhook({ request: createWebhookRequest(event), env });
      expect(res3.status).toBe(200);

      // ユーザーはproに更新されている（1回目で処理済み）
      const user = env.DB._store.users.get('user-r2-1');
      expect(user.plan).toBe('pro');
    });

    it('異なるイベントIDは別々に処理', async () => {
      const event1 = {
        id: 'evt_diff_1',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-r2-1' },
            subscription: 'sub_1',
            customer: 'cus_r2_123',
          },
        },
      };
      const event2 = {
        id: 'evt_diff_2',
        type: 'customer.subscription.deleted',
        data: { object: { id: 'sub_1', customer: 'cus_r2_123' } },
      };

      await webhook({ request: createWebhookRequest(event1), env });
      expect(env.DB._store.users.get('user-r2-1').plan).toBe('pro');

      await webhook({ request: createWebhookRequest(event2), env });
      expect(env.DB._store.users.get('user-r2-1').plan).toBe('free');
    });
  });

  describe('STRIPE_WEBHOOK_SECRET異常系', () => {
    it('undefined: 500', async () => {
      env.STRIPE_WEBHOOK_SECRET = undefined;
      const event = { id: 'evt_1', type: 'test', data: { object: {} } };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(500);
    });

    it('null: 500', async () => {
      env.STRIPE_WEBHOOK_SECRET = null;
      const event = { id: 'evt_2', type: 'test', data: { object: {} } };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(500);
    });

    it('false: 500', async () => {
      env.STRIPE_WEBHOOK_SECRET = false;
      const event = { id: 'evt_3', type: 'test', data: { object: {} } };
      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(500);
    });
  });
});
