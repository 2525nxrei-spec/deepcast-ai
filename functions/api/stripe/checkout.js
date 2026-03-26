/**
 * POST /api/stripe/checkout — Stripe Checkout Session作成
 * 認証必須。Stripe顧客の確認/作成後、サブスクリプション用Checkoutセッションを生成
 * DeepCast Pro: 150円/月
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  const user = await authenticateUser(request, env);
  if (!user) return errorResponse('認証が必要です', 401);

  try {
    const priceId = env.STRIPE_PRICE_PRO;
    if (!priceId) return errorResponse('Price IDが設定されていません', 500);

    // Stripe顧客の確認/作成（初回のみ）
    let stripeCustomerId = user.stripe_customer_id;
    if (!stripeCustomerId) {
      const customer = await stripeRequest('customers', 'POST', {
        email: user.email,
        name: user.display_name || user.email,
        metadata: { deepcast_user_id: user.id },
      }, env.STRIPE_SECRET_KEY);
      stripeCustomerId = customer.id;
      await env.DB
        .prepare("UPDATE users SET stripe_customer_id = ?, updated_at = datetime('now') WHERE id = ?")
        .bind(stripeCustomerId, user.id)
        .run();
    }

    // Embedded Checkout: ページ内埋め込み決済（リダイレクトなし）
    const frontendUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
    const session = await stripeRequest('checkout/sessions', 'POST', {
      mode: 'subscription',
      ui_mode: 'embedded',
      customer: stripeCustomerId,
      locale: 'ja',
      'line_items[0][price]': priceId,
      'line_items[0][quantity]': '1',
      return_url: `${frontendUrl}/pages/account.html?session_id={CHECKOUT_SESSION_ID}`,
      metadata: { user_id: user.id },
      subscription_data: { metadata: { user_id: user.id } },
    }, env.STRIPE_SECRET_KEY);

    console.log(`Checkout作成: session=${session.id}, user=${user.id}`);
    return jsonResponse({ clientSecret: session.client_secret });
  } catch (err) {
    console.error('Checkoutエラー:', err.message);
    return errorResponse('決済セッションの作成に失敗しました', 500);
  }
}
