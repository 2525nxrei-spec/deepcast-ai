/**
 * POST /api/stripe/portal — Stripe Customer Portal URL生成
 * 認証必須。サブスクリプション管理画面へのURLを返却
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  // 環境変数チェック（502 Bad Gateway防止）
  if (!env.STRIPE_SECRET_KEY) {
    console.error('Portal: STRIPE_SECRET_KEYが未設定');
    return errorResponse('決済サービスが利用できません。管理者にお問い合わせください。', 500);
  }

  let user;
  try {
    user = await authenticateUser(request, env);
  } catch (err) {
    console.error('Portal認証エラー:', err.message);
    return errorResponse('認証処理でエラーが発生しました', 500);
  }
  if (!user) return errorResponse('認証が必要です', 401);
  if (!user.stripe_customer_id) return errorResponse('サブスクリプション情報がありません', 400);

  try {
    const frontendUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
    const session = await stripeRequest('billing_portal/sessions', 'POST', {
      customer: user.stripe_customer_id,
      return_url: `${frontendUrl}/pages/account.html`,
    }, env.STRIPE_SECRET_KEY);

    return jsonResponse({ portal_url: session.url });
  } catch (err) {
    console.error('Portalエラー:', err.message);
    return errorResponse('ポータルの作成に失敗しました', 500);
  }
}
