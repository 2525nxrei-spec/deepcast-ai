/**
 * POST /api/stripe/portal — Stripe Customer Portal URL生成
 * 認証必須。サブスクリプション管理画面へのURLを返却
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
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
