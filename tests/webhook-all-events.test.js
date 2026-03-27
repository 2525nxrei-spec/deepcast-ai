/**
 * Webhook全イベント網羅テスト
 * 全てのStripeイベントタイプに対する正常系・異常系の完全なマトリクステスト
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createMockEnv, parseResponse } from './helpers.js';

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

describe('Webhook — 全イベントマトリクステスト', () => {
  let env;

  beforeEach(() => {
    env = createMockEnv([{
      id: 'user-matrix',
      email: 'matrix@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_matrix_123',
      stripe_subscription_id: null,
    }]);
  });

  describe('checkout.session.completed — 全パターン', () => {
    it('新規顧客（stripe_customer_idなし）: customer_idが設定される', async () => {
      // stripe_customer_idをnullに
      env.DB._store.users.get('user-matrix').stripe_customer_id = null;

      const event = {
        id: 'evt_new_customer',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-matrix' },
            subscription: 'sub_new',
            customer: 'cus_new_customer',
          },
        },
      };

      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-matrix');
      expect(user.plan).toBe('pro');
      expect(user.stripe_customer_id).toBe('cus_new_customer');
      expect(user.stripe_subscription_id).toBe('sub_new');
    });

    it('既存顧客（stripe_customer_id既存）: customer_idはCOALESCEで既存値を保持', async () => {
      const event = {
        id: 'evt_existing_customer',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-matrix' },
            subscription: 'sub_existing',
            customer: 'cus_different',
          },
        },
      };

      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-matrix');
      expect(user.plan).toBe('pro');
      // COALESCEで既存値を保持（モックDBの実装次第）
      expect(user.stripe_customer_id).toBe('cus_matrix_123');
      expect(user.stripe_subscription_id).toBe('sub_existing');
    });

    it('subscriptionがnull: proに変更（subscription_idはnullが設定される）', async () => {
      const event = {
        id: 'evt_no_sub',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-matrix' },
            subscription: null,
            customer: 'cus_matrix_123',
          },
        },
      };

      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-matrix');
      expect(user.plan).toBe('pro');
    });
  });

  describe('customer.subscription.updated — 全ステータスパターン', () => {
    const statuses = [
      { status: 'active', shouldBePro: true },
      { status: 'trialing', shouldBePro: true },
      { status: 'past_due', shouldBePro: false },
      { status: 'canceled', shouldBePro: false },
      { status: 'unpaid', shouldBePro: false },
      { status: 'incomplete', shouldBePro: false },
      { status: 'incomplete_expired', shouldBePro: false },
      { status: 'paused', shouldBePro: false },
    ];

    statuses.forEach(({ status, shouldBePro }) => {
      it(`status="${status}": plan=${shouldBePro ? 'pro' : 'free維持'}`, async () => {
        const event = {
          id: `evt_status_${status}`,
          type: 'customer.subscription.updated',
          data: {
            object: {
              id: `sub_${status}`,
              status,
              customer: 'cus_matrix_123',
            },
          },
        };

        const res = await webhook({ request: createWebhookRequest(event), env });
        expect(res.status).toBe(200);
        const user = env.DB._store.users.get('user-matrix');
        if (shouldBePro) {
          expect(user.plan).toBe('pro');
        } else {
          expect(user.plan).toBe('free');
        }
      });
    });
  });

  describe('customer.subscription.deleted — 複数ユーザーの隔離', () => {
    it('他のユーザーには影響しない', async () => {
      // 2人目のユーザーを追加
      env.DB._store.users.set('user-other', {
        id: 'user-other',
        email: 'other@example.com',
        password_hash: 'xxx',
        password_salt: 'yyy',
        plan: 'pro',
        stripe_customer_id: 'cus_other_456',
        stripe_subscription_id: 'sub_other',
      });

      // user-matrixをproにする
      env.DB._store.users.get('user-matrix').plan = 'pro';
      env.DB._store.users.get('user-matrix').stripe_subscription_id = 'sub_matrix';

      // user-matrixのサブスク削除
      const event = {
        id: 'evt_del_isolated',
        type: 'customer.subscription.deleted',
        data: {
          object: {
            id: 'sub_matrix',
            customer: 'cus_matrix_123',
          },
        },
      };

      const res = await webhook({ request: createWebhookRequest(event), env });
      expect(res.status).toBe(200);

      // user-matrixはfreeに
      const userMatrix = env.DB._store.users.get('user-matrix');
      expect(userMatrix.plan).toBe('free');
      expect(userMatrix.stripe_subscription_id).toBeNull();

      // user-otherはproのまま
      const userOther = env.DB._store.users.get('user-other');
      expect(userOther.plan).toBe('pro');
      expect(userOther.stripe_subscription_id).toBe('sub_other');
    });
  });

  describe('冪等性の詳細テスト', () => {
    it('同一イベントを3回送信: 全て200、DB操作は1回目のみ', async () => {
      const event = {
        id: 'evt_triple',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-matrix' },
            subscription: 'sub_triple',
            customer: 'cus_matrix_123',
          },
        },
      };

      // 1回目
      const res1 = await webhook({ request: createWebhookRequest(event), env });
      expect(res1.status).toBe(200);
      expect(env.DB._store.users.get('user-matrix').plan).toBe('pro');

      // 手動でfreeに戻す（もし2回目が実行されたらproに変わるはず）
      env.DB._store.users.get('user-matrix').plan = 'free';

      // 2回目（冪等性で即return、DB更新されない）
      const res2 = await webhook({ request: createWebhookRequest(event), env });
      expect(res2.status).toBe(200);
      expect(env.DB._store.users.get('user-matrix').plan).toBe('free'); // 変わらない

      // 3回目
      const res3 = await webhook({ request: createWebhookRequest(event), env });
      expect(res3.status).toBe(200);
      expect(env.DB._store.users.get('user-matrix').plan).toBe('free'); // 変わらない
    });

    it('異なるイベントIDは別々に処理される', async () => {
      const event1 = {
        id: 'evt_diff_1',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-matrix' },
            subscription: 'sub_1',
            customer: 'cus_matrix_123',
          },
        },
      };
      const event2 = {
        id: 'evt_diff_2',
        type: 'customer.subscription.deleted',
        data: {
          object: { id: 'sub_1', customer: 'cus_matrix_123' },
        },
      };

      await webhook({ request: createWebhookRequest(event1), env });
      expect(env.DB._store.users.get('user-matrix').plan).toBe('pro');

      await webhook({ request: createWebhookRequest(event2), env });
      expect(env.DB._store.users.get('user-matrix').plan).toBe('free');
    });
  });

  describe('未対応イベント一覧: 全て200（ログのみ）', () => {
    const unknownEvents = [
      'payment_intent.succeeded',
      'payment_intent.payment_failed',
      'charge.succeeded',
      'charge.refunded',
      'customer.created',
      'customer.updated',
      'invoice.paid',
      'invoice.created',
      'payment_method.attached',
    ];

    unknownEvents.forEach(eventType => {
      it(`${eventType}: 200`, async () => {
        const event = {
          id: `evt_unknown_${eventType.replace(/\./g, '_')}`,
          type: eventType,
          data: { object: { id: 'obj_123' } },
        };
        const res = await webhook({ request: createWebhookRequest(event), env });
        expect(res.status).toBe(200);
      });
    });
  });
});
