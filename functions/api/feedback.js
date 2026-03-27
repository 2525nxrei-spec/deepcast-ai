/**
 * POST /api/feedback — ユーザーフィードバック（機能リクエスト・バグ報告）をD1に保存
 * 認証不要（誰でも送信可能）
 */

import { errorResponse, jsonResponse } from '../lib/response.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const body = await request.json();
    const { name, email, category, content } = body;

    if (!content || !content.trim()) {
      return errorResponse('内容は必須です', 400);
    }

    const validCategories = ['feature', 'bug', 'other'];
    const cat = validCategories.includes(category) ? category : 'other';

    await env.DB
      .prepare('INSERT INTO feedback (name, email, category, content) VALUES (?, ?, ?, ?)')
      .bind(
        (name || '').slice(0, 100),
        (email || '').slice(0, 255),
        cat,
        content.trim().slice(0, 5000)
      )
      .run();

    return jsonResponse({ message: '送信しました' });
  } catch (err) {
    console.error('Feedbackエラー:', err.message);
    return errorResponse('送信に失敗しました', 500);
  }
}
