/**
 * POST /api/auth/register — 新規登録
 * email, password, display_name を受け取り、D1にユーザー作成 → JWT発行
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { hashPassword, generateSalt, generateId, createJWT } from '../../lib/crypto.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const body = await request.json();
    const { email, password, display_name } = body;

    if (!email || !password) return errorResponse('メールアドレスとパスワードは必須です');
    if (password.length < 8) return errorResponse('パスワードは8文字以上で設定してください');

    const emailLower = email.toLowerCase().trim();

    // メール重複チェック
    const existing = await env.DB.prepare('SELECT id FROM users WHERE email = ?').bind(emailLower).first();
    if (existing) return errorResponse('このメールアドレスは既に登録されています', 409);

    const id = generateId();
    const salt = generateSalt();
    const hash = await hashPassword(password, salt);

    await env.DB.prepare(
      `INSERT INTO users (id, email, password_hash, password_salt, display_name, plan)
       VALUES (?, ?, ?, ?, ?, 'free')`
    ).bind(id, emailLower, hash, salt, display_name || null).run();

    const token = await createJWT(
      { sub: id, email: emailLower, plan: 'free', exp: Math.floor(Date.now() / 1000) + 30 * 86400 },
      env.JWT_SECRET
    );

    return jsonResponse({
      token,
      user: { id, email: emailLower, display_name: display_name || null, plan: 'free' },
    }, 201);
  } catch (err) {
    console.error('登録エラー:', err.message);
    return errorResponse('登録処理中にエラーが発生しました', 500);
  }
}
