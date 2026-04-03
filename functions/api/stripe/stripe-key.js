/**
 * GET /api/stripe/stripe-key — Stripe公開鍵を返す（Embedded Checkout用）
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';

export async function onRequestGet(context) {
  try {
    const { env } = context;

    // 空文字の場合もnullとして扱う（wrangler.tomlで空文字定義された場合の対策）
    const publishableKey = env.STRIPE_PUBLISHABLE_KEY && env.STRIPE_PUBLISHABLE_KEY.trim() !== ''
      ? env.STRIPE_PUBLISHABLE_KEY
      : null;

    return jsonResponse({ publishableKey });
  } catch (err) {
    console.error('stripe-key エラー:', err);
    return errorResponse('サーバー内部エラーが発生しました', 500);
  }
}
