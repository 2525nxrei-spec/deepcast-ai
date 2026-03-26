/**
 * GET /api/billing/status — 課金ステータス取得
 * 認証必須。plan, subscription status, next_billing_date を返却
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestGet(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  const status = {
    plan: user.plan || 'free',
    subscription: null,
  };

  // Stripeサブスクリプション情報を取得（存在する場合のみ）
  if (user.stripe_subscription_id && env.STRIPE_SECRET_KEY) {
    try {
      const sub = await stripeRequest(
        `subscriptions/${user.stripe_subscription_id}`, 'GET', null, env.STRIPE_SECRET_KEY
      );
      status.subscription = {
        id: sub.id,
        status: sub.status,
        current_period_end: sub.current_period_end,
        cancel_at_period_end: sub.cancel_at_period_end,
        next_billing_date: sub.current_period_end
          ? new Date(sub.current_period_end * 1000).toISOString() : null,
      };
    } catch (err) {
      console.error('サブスク情報取得エラー:', err.message);
    }
  }

  return jsonResponse(status);
}
