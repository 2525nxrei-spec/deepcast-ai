/**
 * PUT /api/auth/password — パスワード変更
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { hashPassword, generateSalt } from '../../lib/crypto.js';

export async function onRequestPut(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse('リクエストボディが不正です');
  }

  const { current_password, new_password } = body;
  if (!current_password || !new_password) {
    return errorResponse('現在のパスワードと新しいパスワードは必須です');
  }

  if (new_password.length < 8) {
    return errorResponse('新しいパスワードは8文字以上で設定してください');
  }

  if (!/[a-zA-Z]/.test(new_password) || !/[0-9]/.test(new_password)) {
    return errorResponse('パスワードは英字と数字の両方を含めてください');
  }

  // 現在のパスワードを検証
  const dbUser = await env.DB.prepare(
    'SELECT password_hash, password_salt FROM users WHERE id = ?'
  ).bind(user.id).first();

  if (!dbUser) return errorResponse('ユーザーが見つかりません', 404);

  const currentHash = await hashPassword(current_password, dbUser.password_salt);
  if (currentHash !== dbUser.password_hash) {
    return errorResponse('現在のパスワードが正しくありません', 401);
  }

  // 新しいパスワードで更新
  const newSalt = generateSalt();
  const newHash = await hashPassword(new_password, newSalt);

  await env.DB.prepare(
    "UPDATE users SET password_hash = ?, password_salt = ?, updated_at = datetime('now') WHERE id = ?"
  ).bind(newHash, newSalt, user.id).run();

  return jsonResponse({ message: 'パスワードを変更しました' });
}
