/**
 * GET /api/stripe/payments — 支払い履歴取得
 * 認証必須。StripeのInvoice APIから支払い済みインボイスを取得して返す
 * DeepCast Pro: 150円/月
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestGet(context) {
  const { request, env } = context;

  // モックモード（STRIPE_SECRET_KEY未設定時）
  if (!env.STRIPE_SECRET_KEY) {
    return jsonResponse({ payments: [], mock: true });
  }

  let user;
  try {
    user = await authenticateUser(request, env);
  } catch (err) {
    console.error('支払い履歴認証エラー:', err.message);
    return errorResponse('認証処理でエラーが発生しました', 500);
  }
  if (!user) return errorResponse('認証が必要です', 401);

  try {
    // DBからstripe_customer_idを取得
    const dbUser = await env.DB.prepare(
      'SELECT stripe_customer_id FROM users WHERE id = ?'
    ).bind(user.id).first();

    if (!dbUser?.stripe_customer_id) {
      return jsonResponse({ payments: [] });
    }

    // Stripe APIから支払い履歴を取得（最新20件）
    const invoicesData = await stripeRequest(
      `invoices?customer=${dbUser.stripe_customer_id}&limit=20&status=paid`,
      'GET',
      null,
      env.STRIPE_SECRET_KEY
    );

    const invoices = invoicesData.data || [];

    // プラン名の日本語マッピング
    const planNameMap = {
      pro: 'プロプラン',
    };

    // フロントエンドが期待する形式に変換
    const payments = invoices.map((invoice) => {
      const lineItem = invoice.lines?.data?.[0];
      const priceId = lineItem?.price?.id || '';

      // Price IDからプラン名を判定
      let planKey = '';
      if (priceId === env.STRIPE_PRICE_PRO) {
        planKey = 'pro';
      }

      return {
        date: invoice.created ? new Date(invoice.created * 1000).toISOString() : null,
        planName: planNameMap[planKey] || planKey,
        amount: invoice.amount_paid || 0,
        status: invoice.status === 'paid' ? 'succeeded' : invoice.status,
        invoiceId: invoice.id,
        invoicePdf: invoice.invoice_pdf || null,
      };
    });

    return jsonResponse({ payments });
  } catch (err) {
    console.error('支払い履歴取得エラー:', err.message);
    return errorResponse('支払い履歴の取得に失敗しました', 500);
  }
}
