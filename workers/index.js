// ⚠️ 旧実装 — 本番はfunctions/を使用。このファイルは参考用。

/**
 * DeepCast AI — Cloudflare Workers APIハンドラー
 * AIポッドキャスト配信サイトのフリーミアム決済・認証API
 *
 * エンドポイント一覧:
 *   POST /api/auth/register      — 新規登録
 *   POST /api/auth/login         — ログイン
 *   GET  /api/auth/me            — ログインユーザー情報取得
 *   POST /api/stripe/checkout    — Stripe Checkout Session作成
 *   POST /api/stripe/webhook     — Stripe Webhook処理
 *   POST /api/stripe/portal      — Customer Portal作成
 *   GET  /api/billing/status     — 課金ステータス取得
 */

// ============================================================
// 定数
// ============================================================

const STRIPE_API_BASE = 'https://api.stripe.com/v1';

// CORS許可オリジン
const ALLOWED_ORIGINS = [
  'https://deepcast-ai.com',
  'http://localhost:8791',
  'http://localhost:3000',
];

// ============================================================
// ユーティリティ: レスポンス生成
// ============================================================

function errorResponse(message, code = 400) {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status: code,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function withCORS(response, origin) {
  const headers = new Headers(response.headers);
  // 許可リストに含まれるオリジンのみ許可
  const allowedOrigin = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  headers.set('Access-Control-Allow-Origin', allowedOrigin);
  headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  headers.set('Access-Control-Max-Age', '86400');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// ============================================================
// ユーティリティ: 暗号・認証
// ============================================================

async function hashPassword(password, salt) {
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits']
  );
  const derivedBits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: encoder.encode(salt), iterations: 100000, hash: 'SHA-256' },
    keyMaterial, 256
  );
  return Array.from(new Uint8Array(derivedBits)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function generateSalt() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array).map(b => b.toString(16).padStart(2, '0')).join('');
}

function generateId() {
  return crypto.randomUUID();
}

function base64urlEncode(data) {
  if (typeof data === 'string') data = new TextEncoder().encode(data);
  const base64 = btoa(String.fromCharCode(...new Uint8Array(data)));
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64urlDecode(str) {
  str = str.replace(/-/g, '+').replace(/_/g, '/');
  while (str.length % 4) str += '=';
  const binary = atob(str);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function createJWT(payload, secret) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encodedHeader = base64urlEncode(JSON.stringify(header));
  const encodedPayload = base64urlEncode(JSON.stringify(payload));
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(signingInput));
  return `${signingInput}.${base64urlEncode(signature)}`;
}

async function verifyJWT(token, secret) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const [encodedHeader, encodedPayload, encodedSignature] = parts;
    const signingInput = `${encodedHeader}.${encodedPayload}`;
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
    );
    const signatureBytes = base64urlDecode(encodedSignature);
    const valid = await crypto.subtle.verify('HMAC', key, signatureBytes, encoder.encode(signingInput));
    if (!valid) return null;
    const payload = JSON.parse(new TextDecoder().decode(base64urlDecode(encodedPayload)));
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

// ============================================================
// Stripe APIヘルパー
// ============================================================

function buildFormBody(obj, prefix = '') {
  const params = new URLSearchParams();
  function flatten(o, p) {
    for (const [key, value] of Object.entries(o)) {
      const fullKey = p ? `${p}[${key}]` : key;
      if (value !== null && value !== undefined && typeof value === 'object' && !Array.isArray(value)) {
        flatten(value, fullKey);
      } else if (Array.isArray(value)) {
        value.forEach((item, i) => {
          if (typeof item === 'object' && item !== null) {
            flatten(item, `${fullKey}[${i}]`);
          } else {
            params.append(`${fullKey}[${i}]`, String(item));
          }
        });
      } else if (value !== null && value !== undefined) {
        params.append(fullKey, String(value));
      }
    }
  }
  flatten(obj, prefix);
  return params.toString();
}

async function stripeRequest(endpoint, method, body, apiKey) {
  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  };
  if (body && method !== 'GET') options.body = buildFormBody(body);
  let url = `${STRIPE_API_BASE}/${endpoint}`;
  if (body && method === 'GET') url += '?' + buildFormBody(body);
  const response = await fetch(url, options);
  const data = await response.json();
  if (data.error) {
    const errMsg = data.error.message || 'Stripe APIエラー';
    console.error(`Stripe APIエラー [${endpoint}]:`, JSON.stringify(data.error));
    throw new Error(errMsg);
  }
  return data;
}

// ============================================================
// Stripe Webhook署名検証
// ============================================================

async function verifyStripeSignature(payload, signatureHeader, secret) {
  if (!signatureHeader) throw new Error('Stripe-Signatureヘッダーがありません');
  const elements = signatureHeader.split(',');
  let timestamp = null;
  const signatures = [];
  for (const element of elements) {
    const [key, value] = element.split('=', 2);
    if (key === 't') timestamp = parseInt(value, 10);
    else if (key === 'v1') signatures.push(value);
  }
  if (!timestamp || signatures.length === 0) throw new Error('Stripe-Signatureヘッダーの形式が不正です');
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > 300) throw new Error('Webhookタイムスタンプが許容範囲外です');

  const signedPayload = `${timestamp}.${payload}`;
  const encoder = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signatureBuffer = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(signedPayload));
  const expectedSignature = Array.from(new Uint8Array(signatureBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');

  // タイミングセーフ比較
  const isValid = signatures.some(sig => {
    if (sig.length !== expectedSignature.length) return false;
    let result = 0;
    for (let i = 0; i < sig.length; i++) result |= sig.charCodeAt(i) ^ expectedSignature.charCodeAt(i);
    return result === 0;
  });
  if (!isValid) throw new Error('Webhook署名の検証に失敗しました');
  return JSON.parse(payload);
}

// ============================================================
// 認証ミドルウェア
// ============================================================

async function authenticateUser(request, env) {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader || !authHeader.startsWith('Bearer ')) return null;
  const token = authHeader.substring(7);
  const payload = await verifyJWT(token, env.JWT_SECRET);
  if (!payload || !payload.sub) return null;
  const user = await env.DB
    .prepare('SELECT id, email, display_name, plan, stripe_customer_id, stripe_subscription_id FROM users WHERE id = ?')
    .bind(payload.sub)
    .first();
  return user || null;
}

// ============================================================
// ハンドラ: 認証
// ============================================================

/** POST /api/auth/register */
async function handleRegister(request, env) {
  try {
    const body = await request.json();
    const { email, password, display_name } = body;
    if (!email || !password) return errorResponse('メールアドレスとパスワードは必須です');
    if (password.length < 8) return errorResponse('パスワードは8文字以上で設定してください');

    const emailLower = email.toLowerCase().trim();
    const existing = await env.DB.prepare('SELECT id FROM users WHERE email = ?').bind(emailLower).first();
    if (existing) return errorResponse('このメールアドレスは既に登録されています', 409);

    const id = generateId();
    const salt = generateSalt();
    const hash = await hashPassword(password, salt);

    await env.DB.prepare(
      `INSERT INTO users (id, email, password_hash, salt, display_name, plan)
       VALUES (?, ?, ?, ?, ?, 'free')`
    ).bind(id, emailLower, hash, salt, display_name || null).run();

    const token = await createJWT(
      { sub: id, email: emailLower, plan: 'free', exp: Math.floor(Date.now() / 1000) + 30 * 86400 },
      env.JWT_SECRET
    );

    return jsonResponse({ token, user: { id, email: emailLower, display_name: display_name || null, plan: 'free' } }, 201);
  } catch (err) {
    console.error('登録エラー:', err.message);
    return errorResponse('登録処理中にエラーが発生しました', 500);
  }
}

/** POST /api/auth/login */
async function handleLogin(request, env) {
  try {
    const body = await request.json();
    const { email, password } = body;
    if (!email || !password) return errorResponse('メールアドレスとパスワードを入力してください');

    const emailLower = email.toLowerCase().trim();
    const user = await env.DB
      .prepare('SELECT id, email, display_name, password_hash, salt, plan FROM users WHERE email = ?')
      .bind(emailLower)
      .first();
    if (!user) return errorResponse('メールアドレスまたはパスワードが正しくありません', 401);

    const hash = await hashPassword(password, user.salt);
    if (hash !== user.password_hash) return errorResponse('メールアドレスまたはパスワードが正しくありません', 401);

    const token = await createJWT(
      { sub: user.id, email: user.email, plan: user.plan, exp: Math.floor(Date.now() / 1000) + 30 * 86400 },
      env.JWT_SECRET
    );

    return jsonResponse({
      token,
      user: { id: user.id, email: user.email, display_name: user.display_name, plan: user.plan },
    });
  } catch (err) {
    console.error('ログインエラー:', err.message);
    return errorResponse('ログイン処理中にエラーが発生しました', 500);
  }
}

/** GET /api/auth/me */
async function handleMe(request, env) {
  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);
  return jsonResponse({
    user: { id: user.id, email: user.email, display_name: user.display_name, plan: user.plan },
  });
}

// ============================================================
// ハンドラ: Stripe Checkout
// ============================================================

/** POST /api/stripe/checkout */
async function handleCheckout(request, env) {
  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  try {
    const priceId = env.STRIPE_PRICE_PRO;
    if (!priceId) return errorResponse('Price IDが設定されていません', 500);

    // Stripe顧客の確認/作成
    let stripeCustomerId = user.stripe_customer_id;
    if (!stripeCustomerId) {
      const customer = await stripeRequest('customers', 'POST', {
        email: user.email,
        name: user.display_name || user.email,
        metadata: { deepcast_user_id: user.id },
      }, env.STRIPE_SECRET_KEY);
      stripeCustomerId = customer.id;
      await env.DB
        .prepare("UPDATE users SET stripe_customer_id = ?, updated_at = datetime('now') WHERE id = ?")
        .bind(stripeCustomerId, user.id)
        .run();
    }

    // Checkout Session作成
    const frontendUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
    const session = await stripeRequest('checkout/sessions', 'POST', {
      mode: 'subscription',
      customer: stripeCustomerId,
      'payment_method_types[0]': 'card',
      locale: 'ja',
      'line_items[0][price]': priceId,
      'line_items[0][quantity]': '1',
      success_url: `${frontendUrl}/app/account.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${frontendUrl}/app/pricing.html`,
      metadata: { user_id: user.id },
      subscription_data: { metadata: { user_id: user.id } },
    }, env.STRIPE_SECRET_KEY);

    console.log(`Checkout作成: session=${session.id}, user=${user.id}`);
    return jsonResponse({ checkout_url: session.url });
  } catch (err) {
    console.error('Checkoutエラー:', err.message);
    return errorResponse('決済セッションの作成に失敗しました', 500);
  }
}

// ============================================================
// ハンドラ: Stripe Webhook
// ============================================================

/** POST /api/stripe/webhook */
async function handleWebhook(request, env) {
  try {
    const payload = await request.text();
    const signatureHeader = request.headers.get('stripe-signature');
    if (!env.STRIPE_WEBHOOK_SECRET) {
      console.error('STRIPE_WEBHOOK_SECRETが未設定');
      return errorResponse('Webhook設定エラー', 500);
    }

    let event;
    try {
      event = await verifyStripeSignature(payload, signatureHeader, env.STRIPE_WEBHOOK_SECRET);
    } catch (verifyErr) {
      console.error('Webhook署名検証失敗:', verifyErr.message);
      return errorResponse('署名検証失敗', 400);
    }

    // 冪等性チェック
    const existing = await env.DB
      .prepare('SELECT id FROM webhooks_log WHERE event_id = ?')
      .bind(event.id)
      .first();
    if (existing) {
      console.log(`Webhook冪等性: ${event.id} は処理済み`);
      return jsonResponse({ received: true });
    }

    console.log(`Webhook受信: type=${event.type}, id=${event.id}`);

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const userId = session.metadata?.user_id;
        const subscriptionId = session.subscription;
        const customerId = session.customer;
        if (userId) {
          await env.DB.prepare(
            `UPDATE users SET plan = 'pro', stripe_customer_id = COALESCE(stripe_customer_id, ?),
             stripe_subscription_id = ?, updated_at = datetime('now') WHERE id = ?`
          ).bind(customerId, subscriptionId, userId).run();
          console.log(`Pro開始: user=${userId}`);
        }
        break;
      }
      case 'customer.subscription.updated': {
        const sub = event.data.object;
        if (sub.status === 'active' || sub.status === 'trialing') {
          await env.DB.prepare(
            `UPDATE users SET plan = 'pro', stripe_subscription_id = ?, updated_at = datetime('now')
             WHERE stripe_customer_id = ?`
          ).bind(sub.id, sub.customer).run();
        }
        break;
      }
      case 'customer.subscription.deleted': {
        const sub = event.data.object;
        await env.DB.prepare(
          `UPDATE users SET plan = 'free', stripe_subscription_id = NULL, updated_at = datetime('now')
           WHERE stripe_customer_id = ?`
        ).bind(sub.customer).run();
        console.log(`解約: customer=${sub.customer}`);
        break;
      }
      case 'invoice.payment_failed': {
        const invoice = event.data.object;
        console.error(`支払い失敗: customer=${invoice.customer}, 試行=${invoice.attempt_count}`);
        break;
      }
      default:
        console.log(`未対応: ${event.type}`);
    }

    // Webhookログ記録
    try {
      await env.DB.prepare(
        `INSERT INTO webhooks_log (id, event_type, event_id, processed_at)
         VALUES (?, ?, ?, datetime('now'))`
      ).bind(generateId(), event.type, event.id).run();
    } catch (logErr) {
      if (!logErr.message?.includes('UNIQUE')) console.error('ログ記録エラー:', logErr.message);
    }

    return jsonResponse({ received: true });
  } catch (err) {
    console.error('Webhookエラー:', err.message);
    return errorResponse('Webhook処理エラー', 500);
  }
}

// ============================================================
// ハンドラ: Customer Portal
// ============================================================

/** POST /api/stripe/portal */
async function handlePortal(request, env) {
  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);
  if (!user.stripe_customer_id) return errorResponse('サブスクリプション情報がありません', 400);

  try {
    const frontendUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
    const session = await stripeRequest('billing_portal/sessions', 'POST', {
      customer: user.stripe_customer_id,
      return_url: `${frontendUrl}/app/account.html`,
    }, env.STRIPE_SECRET_KEY);
    return jsonResponse({ portal_url: session.url });
  } catch (err) {
    console.error('Portalエラー:', err.message);
    return errorResponse('ポータルの作成に失敗しました', 500);
  }
}

// ============================================================
// ハンドラ: 課金ステータス
// ============================================================

/** GET /api/billing/status */
async function handleBillingStatus(request, env) {
  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  const status = {
    plan: user.plan || 'free',
    subscription: null,
  };

  if (user.stripe_subscription_id && env.STRIPE_SECRET_KEY) {
    try {
      const sub = await stripeRequest(
        `subscriptions/${user.stripe_subscription_id}`, 'GET', null, env.STRIPE_SECRET_KEY
      );
      status.subscription = {
        id: sub.id,
        status: sub.status,
        current_period_end: sub.current_period_end,
        cancel_at_period_end: sub.cancel_at_period_end,
        next_billing_date: sub.current_period_end
          ? new Date(sub.current_period_end * 1000).toISOString() : null,
      };
    } catch (err) {
      console.error('サブスク情報取得エラー:', err.message);
    }
  }

  return jsonResponse(status);
}

// ============================================================
// メインルーター
// ============================================================

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS preflight
    if (method === 'OPTIONS') {
      return withCORS(new Response(null, { status: 204 }), request.headers.get('Origin'));
    }

    let response;
    try {
      // ルーティング
      if (path === '/api/auth/register' && method === 'POST') {
        response = await handleRegister(request, env);
      } else if (path === '/api/auth/login' && method === 'POST') {
        response = await handleLogin(request, env);
      } else if (path === '/api/auth/me' && method === 'GET') {
        response = await handleMe(request, env);
      } else if (path === '/api/stripe/checkout' && method === 'POST') {
        response = await handleCheckout(request, env);
      } else if (path === '/api/stripe/webhook' && method === 'POST') {
        // WebhookはCORS不要（Stripeから直接呼ばれる）
        return await handleWebhook(request, env);
      } else if (path === '/api/stripe/portal' && method === 'POST') {
        response = await handlePortal(request, env);
      } else if (path === '/api/billing/status' && method === 'GET') {
        response = await handleBillingStatus(request, env);
      } else {
        response = errorResponse('Not Found', 404);
      }
    } catch (err) {
      console.error('予期しないエラー:', err.message, err.stack);
      response = errorResponse('Internal Server Error', 500);
    }

    return withCORS(response, request.headers.get('Origin'));
  },
};
