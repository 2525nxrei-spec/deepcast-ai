/**
 * POST /api/stripe/webhook — 高度なテスト
 * 全イベントタイプ、異常系、エッジケースを網羅
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createMockEnv, parseResponse } from './helpers.js';

// verifyStripeSignatureをモック（署名検証をスキップ）
vi.mock('../functions/lib/stripe.js', () => ({
  stripeRequest: vi.fn(),
  verifyStripeSignature: vi.fn(async (payload) => JSON.parse(payload)),
}));

const { onRequestPost: webhook } = await import('../functions/api/stripe/webhook.js');
const { verifyStripeSignature } = await import('../functions/lib/stripe.js');

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

describe('POST /api/stripe/webhook — 高度なテスト', () => {
  let env;

  beforeEach(() => {
    vi.clearAllMocks();
    verifyStripeSignature.mockImplementation(async (payload) => JSON.parse(payload));
    env = createMockEnv([{
      id: 'user-adv-1',
      email: 'adv-user@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_adv_123',
      stripe_subscription_id: null,
    }]);
  });

  describe('署名検証異常系', () => {
    it('署名検証がエラーを投げた場合: 400', async () => {
      verifyStripeSignature.mockRejectedValueOnce(new Error('署名検証失敗'));

      const event = { id: 'evt_1', type: 'test', data: { object: {} } };
      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(400);
      const json = await parseResponse(res);
      expect(json.error).toContain('署名検証失敗');
    });
  });

  describe('checkout.session.completed 詳細', () => {
    it('metadataにuser_idがない場合: 200だがDB更新なし', async () => {
      const event = {
        id: 'evt_no_userid',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: {},
            subscription: 'sub_123',
            customer: 'cus_adv_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      // ユーザーのプランはfreeのまま
      const user = env.DB._store.users.get('user-adv-1');
      expect(user.plan).toBe('free');
    });

    it('存在しないuser_idでも200（DB更新は空振り）', async () => {
      const event = {
        id: 'evt_nonexist_user',
        type: 'checkout.session.completed',
        data: {
          object: {
            metadata: { user_id: 'user-nonexistent' },
            subscription: 'sub_123',
            customer: 'cus_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
    });
  });

  describe('customer.subscription.updated 詳細', () => {
    it('trialing状態でもproに設定', async () => {
      env.DB._store.users.get('user-adv-1').plan = 'free';
      env.DB._store.users.get('user-adv-1').stripe_customer_id = 'cus_adv_123';

      const event = {
        id: 'evt_trialing',
        type: 'customer.subscription.updated',
        data: {
          object: {
            id: 'sub_trial_123',
            status: 'trialing',
            customer: 'cus_adv_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-adv-1');
      expect(user.plan).toBe('pro');
    });

    it('past_due状態ではproに変更しない', async () => {
      env.DB._store.users.get('user-adv-1').plan = 'free';

      const event = {
        id: 'evt_pastdue',
        type: 'customer.subscription.updated',
        data: {
          object: {
            id: 'sub_pastdue',
            status: 'past_due',
            customer: 'cus_adv_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-adv-1');
      expect(user.plan).toBe('free');
    });

    it('canceled状態ではproに変更しない', async () => {
      env.DB._store.users.get('user-adv-1').plan = 'free';

      const event = {
        id: 'evt_canceled_update',
        type: 'customer.subscription.updated',
        data: {
          object: {
            id: 'sub_canceled',
            status: 'canceled',
            customer: 'cus_adv_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-adv-1');
      expect(user.plan).toBe('free');
    });

    it('存在しないcustomer_idのsubscription.updated: 200（空振り）', async () => {
      const event = {
        id: 'evt_unknown_cus',
        type: 'customer.subscription.updated',
        data: {
          object: {
            id: 'sub_x',
            status: 'active',
            customer: 'cus_nonexistent',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
    });
  });

  describe('customer.subscription.deleted 詳細', () => {
    it('既にfreeのユーザーにdeleted: 200（冪等）', async () => {
      // ユーザーは既にfree
      const event = {
        id: 'evt_del_already_free',
        type: 'customer.subscription.deleted',
        data: {
          object: {
            id: 'sub_old',
            customer: 'cus_adv_123',
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const user = env.DB._store.users.get('user-adv-1');
      expect(user.plan).toBe('free');
    });
  });

  describe('未対応イベント', () => {
    it('未知のイベントタイプ: 200（ログのみ）', async () => {
      const event = {
        id: 'evt_unknown_type',
        type: 'payment_intent.succeeded',
        data: { object: {} },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
      const json = await parseResponse(res);
      expect(json.received).toBe(true);
    });
  });

  describe('invoice.payment_failed 詳細', () => {
    it('attempt_countが大きい場合でも200', async () => {
      const event = {
        id: 'evt_fail_high_attempts',
        type: 'invoice.payment_failed',
        data: {
          object: {
            customer: 'cus_adv_123',
            attempt_count: 10,
          },
        },
      };

      const res = await webhook({
        request: createWebhookRequest(event),
        env,
      });
      expect(res.status).toBe(200);
    });
  });
});
