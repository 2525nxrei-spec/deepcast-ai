/**
 * GET /api/auth/me — ログインユーザー情報取得
 * Authorization Bearerトークンを検証し、ユーザー情報を返却
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';

export async function onRequestGet(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  return jsonResponse({
    user: { id: user.id, email: user.email, display_name: user.display_name, plan: user.plan },
  });
}
