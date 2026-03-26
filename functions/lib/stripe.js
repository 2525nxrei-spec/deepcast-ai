/**
 * Stripe APIヘルパー・Webhook署名検証
 */

const STRIPE_API_BASE = 'https://api.stripe.com/v1';

function buildFormBody(obj, prefix = '') {
  const params = new URLSearchParams();
  function flatten(o, p) {
    for (const [key, value] of Object.entries(o)) {
      const fullKey = p ? `${p}[${key}]` : key;
      if (value !== null && value !== undefined && typeof value === 'object' && !Array.isArray(value)) {
        flatten(value, fullKey);
      } else if (Array.isArray(value)) {
        value.forEach((item, i) => {
          if (typeof item === 'object' && item !== null) {
            flatten(item, `${fullKey}[${i}]`);
          } else {
            params.append(`${fullKey}[${i}]`, String(item));
          }
        });
      } else if (value !== null && value !== undefined) {
        params.append(fullKey, String(value));
      }
    }
  }
  flatten(obj, prefix);
  return params.toString();
}

export async function stripeRequest(endpoint, method, body, apiKey) {
  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  };
  if (body && method !== 'GET') options.body = buildFormBody(body);
  let url = `${STRIPE_API_BASE}/${endpoint}`;
  if (body && method === 'GET') url += '?' + buildFormBody(body);

  const response = await fetch(url, options);
  const data = await response.json();
  if (data.error) {
    const errMsg = data.error.message || 'Stripe APIエラー';
    console.error(`Stripe APIエラー [${endpoint}]:`, JSON.stringify(data.error));
    throw new Error(errMsg);
  }
  return data;
}

export async function verifyStripeSignature(payload, signatureHeader, secret) {
  if (!signatureHeader) throw new Error('Stripe-Signatureヘッダーがありません');

  const elements = signatureHeader.split(',');
  let timestamp = null;
  const signatures = [];
  for (const element of elements) {
    const [key, value] = element.split('=', 2);
    if (key === 't') timestamp = parseInt(value, 10);
    else if (key === 'v1') signatures.push(value);
  }
  if (!timestamp || signatures.length === 0) throw new Error('Stripe-Signatureヘッダーの形式が不正です');

  // タイムスタンプの許容範囲: 5分
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - timestamp) > 300) throw new Error('Webhookタイムスタンプが許容範囲外です');

  const signedPayload = `${timestamp}.${payload}`;
  const encoder = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signatureBuffer = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(signedPayload));
  const expectedSignature = Array.from(new Uint8Array(signatureBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');

  // タイミングセーフ比較（定数時間比較でサイドチャネル攻撃を防止）
  const isValid = signatures.some(sig => {
    if (sig.length !== expectedSignature.length) return false;
    let result = 0;
    for (let i = 0; i < sig.length; i++) result |= sig.charCodeAt(i) ^ expectedSignature.charCodeAt(i);
    return result === 0;
  });
  if (!isValid) throw new Error('Webhook署名の検証に失敗しました');

  return JSON.parse(payload);
}
