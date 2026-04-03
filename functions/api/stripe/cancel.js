/**
 * POST /api/stripe/cancel — サブスクリプション解約
 * 認証必須。即時解約ではなく、現在の請求期間終了時に解約（cancel_at_period_end）
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';
import { stripeRequest } from '../../lib/stripe.js';

export async function onRequestPost(context) {
  const { request, env } = context;

  // 環境変数チェック
  if (!env.STRIPE_SECRET_KEY) {
    console.error('STRIPE_SECRET_KEY が設定されていません');
    return errorResponse('決済システムの設定エラーが発生しました。管理者にお問い合わせください。', 500);
  }

  let user;
  try {
    user = await authenticateUser(request, env);
  } catch (err) {
    console.error('解約認証エラー:', err.message);
    return errorResponse('認証処理でエラーが発生しました', 500);
  }
  if (!user) return errorResponse('認証が必要です', 401);
  if (!user.stripe_customer_id) return errorResponse('サブスクリプション情報がありません', 400);

  try {
    // サブスクリプションIDの取得
    let subscriptionId = user.stripe_subscription_id;

    // DBにない場合はStripe APIから取得
    if (!subscriptionId) {
      const subsData = await stripeRequest(
        `subscriptions?customer=${encodeURIComponent(user.stripe_customer_id)}&status=active&limit=1`,
        'GET',
        null,
        env.STRIPE_SECRET_KEY
      );

      if (!subsData.data || subsData.data.length === 0) {
        return errorResponse('アクティブなサブスクリプションが見つかりません', 404);
      }

      subscriptionId = subsData.data[0].id;
    }

    // サブスクリプションを期間終了時に解約
    const subscription = await stripeRequest(
      `subscriptions/${subscriptionId}`,
      'POST',
      { cancel_at_period_end: 'true' },
      env.STRIPE_SECRET_KEY
    );

    // DBのフラグを更新
    await env.DB
      .prepare("UPDATE users SET cancel_at_period_end = 1, updated_at = datetime('now') WHERE id = ?")
      .bind(user.id)
      .run();

    console.log(`サブスクリプション解約: user=${user.id}, subscription=${subscriptionId}`);

    return jsonResponse({
      canceled: true,
      cancel_at_period_end: true,
      current_period_end: subscription.current_period_end,
      message: '解約が完了しました。現在の請求期間の終了までサービスをご利用いただけます。',
    });
  } catch (err) {
    console.error('解約エラー:', err.message);
    return errorResponse('サブスクリプションの解約に失敗しました', 500);
  }
}
