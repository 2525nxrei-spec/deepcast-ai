/**
 * テストヘルパー — D1モック、env モック、リクエスト生成
 * 外部API（Stripe, Gemini等）は一切呼ばない設計
 */

/**
 * インメモリD1モック
 * prepare → bind → first/run/all をチェーンで再現
 */
export function createMockDB(rows = []) {
  const store = {
    users: new Map(),
    webhooks_log: new Map(),
  };

  // 初期データ投入
  for (const row of rows) {
    if (row._table === 'webhooks_log') {
      store.webhooks_log.set(row.stripe_event_id || row.id, { ...row });
    } else {
      store.users.set(row.id, { ...row });
    }
  }

  function createStatement(sql) {
    let boundParams = [];

    const statement = {
      bind(...params) {
        boundParams = params;
        return statement;
      },

      async first() {
        const sqlLower = sql.toLowerCase();

        // SELECT by email
        if (sqlLower.includes('from users where email')) {
          const email = boundParams[0];
          for (const user of store.users.values()) {
            if (user.email === email) return { ...user };
          }
          return null;
        }

        // SELECT by id
        if (sqlLower.includes('from users where id')) {
          const id = boundParams[0];
          return store.users.has(id) ? { ...store.users.get(id) } : null;
        }

        // SELECT by stripe_customer_id
        if (sqlLower.includes('from users where stripe_customer_id')) {
          const customerId = boundParams[0];
          for (const user of store.users.values()) {
            if (user.stripe_customer_id === customerId) return { ...user };
          }
          return null;
        }

        // Webhook冪等性チェック
        if (sqlLower.includes('from webhooks_log where stripe_event_id')) {
          const eventId = boundParams[0];
          return store.webhooks_log.has(eventId) ? { id: eventId } : null;
        }

        return null;
      },

      async run() {
        const sqlLower = sql.toLowerCase();

        // INSERT INTO users
        if (sqlLower.includes('insert into users')) {
          const [id, email, hash, salt, displayName] = boundParams;
          store.users.set(id, {
            id, email, password_hash: hash, password_salt: salt,
            display_name: displayName, plan: 'free',
            stripe_customer_id: null, stripe_subscription_id: null,
          });
          return { success: true };
        }

        // UPDATE users SET plan = 'pro' (checkout.session.completed)
        if (sqlLower.includes("plan = 'pro'") && sqlLower.includes('stripe_subscription_id')) {
          if (sqlLower.includes('where id')) {
            // bind: customerId, subscriptionId, userId
            const userId = boundParams[boundParams.length - 1];
            const user = store.users.get(userId);
            if (user) {
              user.plan = 'pro';
              user.stripe_customer_id = user.stripe_customer_id || boundParams[0];
              user.stripe_subscription_id = boundParams[1];
            }
          } else if (sqlLower.includes('where stripe_customer_id')) {
            // subscription.updated: bind(sub.id, sub.customer)
            const subId = boundParams[0];
            const customerId = boundParams[1];
            for (const user of store.users.values()) {
              if (user.stripe_customer_id === customerId) {
                user.plan = 'pro';
                user.stripe_subscription_id = subId;
              }
            }
          }
          return { success: true };
        }

        // UPDATE users SET plan = 'free' (subscription.deleted)
        if (sqlLower.includes("plan = 'free'")) {
          const customerId = boundParams[0];
          for (const user of store.users.values()) {
            if (user.stripe_customer_id === customerId) {
              user.plan = 'free';
              user.stripe_subscription_id = null;
            }
          }
          return { success: true };
        }

        // UPDATE stripe_customer_id
        if (sqlLower.includes('stripe_customer_id') && sqlLower.includes('update')) {
          const customerId = boundParams[0];
          const userId = boundParams[1];
          const user = store.users.get(userId);
          if (user) user.stripe_customer_id = customerId;
          return { success: true };
        }

        // UPDATE password
        if (sqlLower.includes('password_hash') && sqlLower.includes('password_salt') && sqlLower.includes('update')) {
          const newHash = boundParams[0];
          const newSalt = boundParams[1];
          const userId = boundParams[2];
          const user = store.users.get(userId);
          if (user) {
            user.password_hash = newHash;
            user.password_salt = newSalt;
          }
          return { success: true };
        }

        // DELETE FROM users
        if (sqlLower.includes('delete from users')) {
          const id = boundParams[0];
          store.users.delete(id);
          return { success: true };
        }

        // INSERT INTO webhooks_log
        if (sqlLower.includes('insert into webhooks_log')) {
          const [id, eventType, stripeEventId] = boundParams;
          store.webhooks_log.set(stripeEventId, { id, event_type: eventType, stripe_event_id: stripeEventId });
          return { success: true };
        }

        return { success: true };
      },

      async all() {
        return { results: [] };
      },
    };

    return statement;
  }

  return {
    prepare: (sql) => createStatement(sql),
    _store: store,
  };
}

/**
 * テスト用env生成
 */
export function createMockEnv(dbRows = []) {
  return {
    DB: createMockDB(dbRows),
    JWT_SECRET: 'test-jwt-secret-key-for-ci',
    STRIPE_SECRET_KEY: 'sk_test_fake_key',
    STRIPE_WEBHOOK_SECRET: 'whsec_test_fake_secret',
    STRIPE_PRICE_PRO: 'price_test_fake_id',
    STRIPE_PUBLISHABLE_KEY: 'pk_test_fake_key',
    FRONTEND_URL: 'https://deepcast-ai.com',
  };
}

/**
 * テスト用Requestオブジェクト生成
 */
export function createRequest(method, url, body = null, headers = {}) {
  const init = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Origin': 'https://deepcast-ai.com',
      ...headers,
    },
  };
  if (body && method !== 'GET') {
    init.body = JSON.stringify(body);
  }
  return new Request(url, init);
}

/**
 * レスポンスのJSONパース
 */
export async function parseResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return { _raw: text };
  }
}
