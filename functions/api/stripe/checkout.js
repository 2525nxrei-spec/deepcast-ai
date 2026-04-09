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

  // 環境変数チェック（502 Bad Gateway防止）
  if (!env.STRIPE_SECRET_KEY) {
    console.error('Checkout: STRIPE_SECRET_KEYが未設定');
    return errorResponse('決済サービスが利用できません。管理者にお問い合わせください。', 500);
  }

  let user;
  try {
    user = await authenticateUser(request, env);
  } catch (err) {
    console.error('Checkout認証エラー:', err.message);
    return errorResponse('認証処理でエラーが発生しました', 500);
  }
  if (!user) return errorResponse('認証が必要です', 401);

  // Pro重複決済ガード
  if (user.plan === 'pro') {
    return errorResponse('すでにProプランをご利用中です', 400);
  }

  try {
    const priceId = env.STRIPE_PRICE_PRO;
    if (!priceId) {
      console.error('Checkout: STRIPE_PRICE_PROが未設定。Cloudflareダッシュボードで環境変数を設定してください。');
      return errorResponse('決済サービスの設定が不完全です。管理者にお問い合わせください。', 500);
    }

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

    // リダイレクト型 Stripe Checkout
    const frontendUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
    const session = await stripeRequest('checkout/sessions', 'POST', {
      mode: 'subscription',
      customer: stripeCustomerId,
      locale: 'ja',
      payment_method_types: ['card'],
      line_items: [{ price: priceId, quantity: '1' }],
      success_url: `${frontendUrl}/pages/account.html?payment=success&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${frontendUrl}/pages/account.html?payment=cancel`,
      metadata: { user_id: user.id },
      subscription_data: { metadata: { user_id: user.id } },
    }, env.STRIPE_SECRET_KEY);

    console.log(`Checkout作成: session=${session.id}, user=${user.id}`);
    return jsonResponse({ url: session.url });
  } catch (err) {
    console.error('Checkoutエラー:', err.message);
    return errorResponse('決済セッションの作成に失敗しました', 500);
  }
}
