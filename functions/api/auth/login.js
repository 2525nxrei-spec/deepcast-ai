/**
 * POST /api/auth/login — ログイン
 * email, password を検証し、JWT発行
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { hashPassword, createJWT } from '../../lib/crypto.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const body = await request.json();
    const { email, password } = body;
    if (!email || !password) return errorResponse('メールアドレスとパスワードを入力してください');

    const emailLower = email.toLowerCase().trim();
    const user = await env.DB
      .prepare('SELECT id, email, display_name, password_hash, password_salt, plan FROM users WHERE email = ?')
      .bind(emailLower)
      .first();
    if (!user) return errorResponse('メールアドレスまたはパスワードが正しくありません', 401);

    const hash = await hashPassword(password, user.password_salt);
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
