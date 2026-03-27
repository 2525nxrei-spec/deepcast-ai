/**
 * Webhook DB異常系テスト
 * DB操作がエラーを返した場合の耐障害性を検証
 * webhooks_log UNIQUE制約違反、DB接続エラー等
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

describe('Webhook DB異常系テスト', () => {
  let env;

  beforeEach(() => {
    env = createMockEnv([{
      id: 'user-db-err',
      email: 'db-err@example.com',
      password_hash: 'xxx',
      password_salt: 'yyy',
      plan: 'free',
      stripe_customer_id: 'cus_db_123',
      stripe_subscription_id: null,
    }]);
  });

  it('webhooks_log INSERT時のUNIQUE制約違反: 正常終了（200）', async () => {
    // webhooks_logのINSERTでUNIQUE制約違反をシミュレート
    const originalPrepare = env.DB.prepare;
    let insertCount = 0;
    env.DB.prepare = (sql) => {
      const stmt = originalPrepare(sql);
      if (sql.toLowerCase().includes('insert into webhooks_log')) {
        const originalRun = stmt.run.bind(stmt);
        stmt.run = async function() {
          insertCount++;
          throw new Error('UNIQUE constraint failed: webhooks_log.stripe_event_id');
        };
      }
      return stmt;
    };

    const event = {
      id: 'evt_unique_test',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: 'user-db-err' },
          subscription: 'sub_123',
          customer: 'cus_db_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(200);
    const json = await parseResponse(res);
    expect(json.received).toBe(true);
    // UNIQUE制約違反のINSERTが試みられた
    expect(insertCount).toBe(1);
  });

  it('webhooks_log INSERT時の一般エラー: 正常終了（200、エラーはログ出力のみ）', async () => {
    const originalPrepare = env.DB.prepare;
    env.DB.prepare = (sql) => {
      const stmt = originalPrepare(sql);
      if (sql.toLowerCase().includes('insert into webhooks_log')) {
        stmt.run = async function() {
          throw new Error('Database connection lost');
        };
      }
      return stmt;
    };

    const event = {
      id: 'evt_db_error',
      type: 'invoice.payment_failed',
      data: {
        object: {
          customer: 'cus_db_123',
          attempt_count: 1,
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    // webhooks_logへの記録失敗でも、メイン処理は成功するので200
    expect(res.status).toBe(200);
  });

  it('冪等性チェック（SELECT）でDBエラー: 500', async () => {
    const originalPrepare = env.DB.prepare;
    env.DB.prepare = (sql) => {
      const stmt = originalPrepare(sql);
      if (sql.toLowerCase().includes('from webhooks_log where stripe_event_id')) {
        stmt.first = async function() {
          throw new Error('Database read error');
        };
      }
      return stmt;
    };

    const event = {
      id: 'evt_select_error',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: 'user-db-err' },
          subscription: 'sub_123',
          customer: 'cus_db_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    // トップレベルのtry-catchに引っかかるので500
    expect(res.status).toBe(500);
  });

  it('checkout.session.completedのUPDATE失敗: 500', async () => {
    const originalPrepare = env.DB.prepare;
    env.DB.prepare = (sql) => {
      const stmt = originalPrepare(sql);
      if (sql.toLowerCase().includes("plan = 'pro'") && sql.toLowerCase().includes('where id')) {
        stmt.run = async function() {
          throw new Error('UPDATE failed');
        };
      }
      return stmt;
    };

    const event = {
      id: 'evt_update_fail',
      type: 'checkout.session.completed',
      data: {
        object: {
          metadata: { user_id: 'user-db-err' },
          subscription: 'sub_123',
          customer: 'cus_db_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(500);
  });

  it('subscription.deletedのUPDATE失敗: 500', async () => {
    env.DB._store.users.get('user-db-err').plan = 'pro';
    env.DB._store.users.get('user-db-err').stripe_subscription_id = 'sub_old';

    const originalPrepare = env.DB.prepare;
    env.DB.prepare = (sql) => {
      const stmt = originalPrepare(sql);
      if (sql.toLowerCase().includes("plan = 'free'")) {
        stmt.run = async function() {
          throw new Error('UPDATE failed on delete');
        };
      }
      return stmt;
    };

    const event = {
      id: 'evt_del_fail',
      type: 'customer.subscription.deleted',
      data: {
        object: {
          id: 'sub_old',
          customer: 'cus_db_123',
        },
      },
    };

    const res = await webhook({ request: createWebhookRequest(event), env });
    expect(res.status).toBe(500);
  });
});
