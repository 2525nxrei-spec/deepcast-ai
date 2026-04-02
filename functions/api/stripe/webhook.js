/**
 * POST /api/stripe/webhook — Stripe Webhook処理
 * 注意: CORSはミドルウェアでスキップされる（Stripeから直接呼ばれるため）
 *
 * 対応イベント:
 *   checkout.session.completed — Pro開始
 *   customer.subscription.updated — ステータス同期
 *   customer.subscription.deleted — 解約処理
 *   invoice.payment_succeeded — 支払い成功（updated_at更新）
 *   invoice.payment_failed — 支払い失敗ログ
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { generateId } from '../../lib/crypto.js';
import { verifyStripeSignature } from '../../lib/stripe.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  try {
    const payload = await request.text();
    const signatureHeader = request.headers.get('stripe-signature');

    if (!env.STRIPE_WEBHOOK_SECRET) {
      console.error('STRIPE_WEBHOOK_SECRETが未設定');
      return errorResponse('Webhook設定エラー', 500);
    }

    // Stripe署名検証（HMAC-SHA256、タイミングセーフ比較）
    let event;
    try {
      event = await verifyStripeSignature(payload, signatureHeader, env.STRIPE_WEBHOOK_SECRET);
    } catch (verifyErr) {
      console.error('Webhook署名検証失敗:', verifyErr.message);
      return errorResponse('署名検証失敗', 400);
    }

    // 冪等性チェック: webhooks_logテーブルでイベントID重複を確認
    const existing = await env.DB
      .prepare('SELECT id FROM webhooks_log WHERE stripe_event_id = ?')
      .bind(event.id)
      .first();
    if (existing) {
      console.log(`Webhook冪等性: ${event.id} は処理済み`);
      return jsonResponse({ received: true });
    }

    console.log(`Webhook受信: type=${event.type}, id=${event.id}`);

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const userId = session.metadata?.user_id;
        const subscriptionId = session.subscription;
        const customerId = session.customer;
        if (userId) {
          await env.DB.prepare(
            `UPDATE users SET plan = 'pro', cancel_at_period_end = 0, stripe_customer_id = COALESCE(stripe_customer_id, ?),
             stripe_subscription_id = ?, updated_at = datetime('now') WHERE id = ?`
          ).bind(customerId, subscriptionId, userId).run();
          console.log(`Pro開始: user=${userId}`);
        }
        break;
      }
      case 'customer.subscription.updated': {
        const sub = event.data.object;
        if (sub.status === 'active' || sub.status === 'trialing') {
          await env.DB.prepare(
            `UPDATE users SET plan = 'pro', cancel_at_period_end = ?, stripe_subscription_id = ?, updated_at = datetime('now')
             WHERE stripe_customer_id = ?`
          ).bind(sub.cancel_at_period_end ? 1 : 0, sub.id, sub.customer).run();
        }
        break;
      }
      case 'customer.subscription.deleted': {
        const sub = event.data.object;
        await env.DB.prepare(
          `UPDATE users SET plan = 'free', stripe_subscription_id = NULL, updated_at = datetime('now')
           WHERE stripe_customer_id = ?`
        ).bind(sub.customer).run();
        console.log(`解約: customer=${sub.customer}`);
        break;
      }
      case 'invoice.payment_succeeded': {
        const invoice = event.data.object;
        const customerId = invoice.customer;
        const subscriptionId = invoice.subscription;
        const amountPaid = invoice.amount_paid;

        await env.DB.prepare(
          `UPDATE users SET updated_at = datetime('now') WHERE stripe_customer_id = ?`
        ).bind(customerId).run();

        console.log(`支払い成功: customer=${customerId}, subscription=${subscriptionId}, amount=${amountPaid}円`);
        break;
      }
      case 'invoice.payment_failed': {
        const invoice = event.data.object;
        console.error(`支払い失敗: customer=${invoice.customer}, 試行=${invoice.attempt_count}`);
        break;
      }
      default:
        console.log(`未対応イベント: ${event.type}`);
    }

    // Webhookログ記録（冪等性保証用）
    try {
      await env.DB.prepare(
        `INSERT INTO webhooks_log (id, event_type, stripe_event_id, payload, processed_at)
         VALUES (?, ?, ?, ?, datetime('now'))`
      ).bind(generateId(), event.type, event.id, JSON.stringify(event)).run();
    } catch (logErr) {
      // UNIQUE制約違反は無視（並行リクエストでの重複処理防止）
      if (!logErr.message?.includes('UNIQUE')) console.error('ログ記録エラー:', logErr.message);
    }

    return jsonResponse({ received: true });
  } catch (err) {
    console.error('Webhookエラー:', err.message);
    return errorResponse('Webhook処理エラー', 500);
  }
}
