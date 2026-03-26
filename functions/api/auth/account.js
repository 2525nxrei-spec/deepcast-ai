/**
 * DELETE /api/auth/account — アカウント削除
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { hashPassword } from '../../lib/crypto.js';

export async function onRequestDelete(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse('リクエストボディが不正です');
  }

  const { password } = body;
  if (!password) return errorResponse('パスワードの入力が必要です');

  // パスワード検証
  const dbUser = await env.DB.prepare(
    'SELECT password_hash, password_salt FROM users WHERE id = ?'
  ).bind(user.id).first();

  if (!dbUser) return errorResponse('ユーザーが見つかりません', 404);

  const hash = await hashPassword(password, dbUser.password_salt);
  if (hash !== dbUser.password_hash) {
    return errorResponse('パスワードが正しくありません', 401);
  }

  // アカウント削除
  await env.DB.prepare('DELETE FROM users WHERE id = ?').bind(user.id).run();

  return jsonResponse({ message: 'アカウントを削除しました。ご利用ありがとうございました。' });
}
