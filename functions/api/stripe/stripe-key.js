/**
 * GET /api/stripe/stripe-key — Stripe公開鍵を返す（Embedded Checkout用）
 */

import { errorResponse, jsonResponse } from '../../lib/response.js';

export async function onRequestGet(context) {
  const { env } = context;

  const publishableKey = env.STRIPE_PUBLISHABLE_KEY || '';
  if (!publishableKey) {
    return errorResponse('Stripe公開鍵が設定されていません', 500);
  }

  return jsonResponse({ publishableKey });
}
