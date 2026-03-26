/**
 * 認証ミドルウェア — JWTからユーザーを取得
 * AuthorizationヘッダーのBearerトークンを検証し、D1からユーザー情報を返す
 */

import { verifyJWT } from './crypto.js';

export async function authenticateUser(request, env) {
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
