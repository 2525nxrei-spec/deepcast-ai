/**
 * グローバルミドルウェア — CORS処理
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
  headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  headers.set('Access-Control-Max-Age', '86400');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export async function onRequest(context) {
  const { request } = context;
  const origin = request.headers.get('Origin');
  const url = new URL(request.url);

  // CORS preflight
  if (request.method === 'OPTIONS') {
    return addCORSHeaders(new Response(null, { status: 204 }), origin);
  }

  // 次のハンドラを実行
  const response = await context.next();

  // Webhookはストライプから直接呼ばれるのでCORS不要
  if (url.pathname === '/api/stripe/webhook') {
    return response;
  }

  return addCORSHeaders(response, origin);
}
