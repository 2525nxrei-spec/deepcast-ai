/**
 * グローバルミドルウェア — CORS処理 + セキュリティヘッダー + レート制限
 * deepcast-ai.comとlocalhostからのリクエストを許可
 * Webhook以外の全APIレスポンスにCORSヘッダーを付与
 */

const ALLOWED_ORIGINS = [
  'https://deepcast-ai.com',
  'https://www.deepcast-ai.com',
  'http://localhost:8788',
  'http://localhost:3000',
];

function isAllowedOrigin(origin) {
  if (!origin) return false;
  return ALLOWED_ORIGINS.some(allowed => origin === allowed);
}

function addCORSHeaders(response, origin) {
  const headers = new Headers(response.headers);
  const allowedOrigin = isAllowedOrigin(origin) ? origin : ALLOWED_ORIGINS[0];
  headers.set('Access-Control-Allow-Origin', allowedOrigin);
  headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  headers.set('Access-Control-Max-Age', '86400');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

/** セキュリティヘッダーを付与 */
function addSecurityHeaders(response) {
  const headers = new Headers(response.headers);
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('X-Frame-Options', 'DENY');
  headers.set('X-XSS-Protection', '1; mode=block');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

/** インメモリレート制限（IP+パスベース） */
const rateLimitMap = new Map();
const RATE_LIMIT_WINDOW = 60 * 1000;
const RATE_LIMIT_MAX_AUTH = 10;
const RATE_LIMIT_MAX_GENERAL = 120;

function isRateLimited(ip, pathname) {
  const now = Date.now();
  const isAuthEndpoint = pathname.includes('/api/auth/login') || pathname.includes('/api/auth/register');
  const limit = isAuthEndpoint ? RATE_LIMIT_MAX_AUTH : RATE_LIMIT_MAX_GENERAL;
  const key = isAuthEndpoint ? `auth:${ip}` : `gen:${ip}`;

  const entry = rateLimitMap.get(key);
  if (!entry || now - entry.start > RATE_LIMIT_WINDOW) {
    rateLimitMap.set(key, { start: now, count: 1 });
    return false;
  }
  entry.count++;
  return entry.count > limit;
}

function cleanupRateLimit() {
  const now = Date.now();
  for (const [key, entry] of rateLimitMap) {
    if (now - entry.start > RATE_LIMIT_WINDOW * 2) {
      rateLimitMap.delete(key);
    }
  }
}

export async function onRequest(context) {
  const { request } = context;
  const origin = request.headers.get('Origin');
  const url = new URL(request.url);

  // CORS preflight
  if (request.method === 'OPTIONS') {
    return addCORSHeaders(new Response(null, { status: 204 }), origin);
  }

  // レート制限チェック（Webhookは除外）
  if (url.pathname !== '/api/stripe/webhook') {
    const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (isRateLimited(clientIP, url.pathname)) {
      return addSecurityHeaders(addCORSHeaders(
        new Response(JSON.stringify({ ok: false, error: 'リクエストが多すぎます。しばらく待ってからお試しください。' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json; charset=utf-8' },
        }),
        origin
      ));
    }
  }

  // 定期クリーンアップ
  if (Math.random() < 0.01) cleanupRateLimit();

  // 次のハンドラを実行（例外発生時もCORSヘッダーを付与）
  let response;
  try {
    response = await context.next();
  } catch (err) {
    console.error('ハンドラ例外:', err);
    response = new Response(JSON.stringify({ ok: false, error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }

  // Webhookはストライプから直接呼ばれるのでCORS不要
  if (url.pathname === '/api/stripe/webhook') {
    return addSecurityHeaders(response);
  }

  return addSecurityHeaders(addCORSHeaders(response, origin));
}
