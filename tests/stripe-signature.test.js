/**
 * Stripe署名検証 (verifyStripeSignature) の単体テスト
 * 実際のHMAC-SHA256署名を生成してテスト（外部API呼び出し禁止）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { verifyStripeSignature } from '../functions/lib/stripe.js';

// テスト用のHMAC-SHA256署名を生成するヘルパー
async function generateTestSignature(payload, secret, timestamp) {
  const signedPayload = `${timestamp}.${payload}`;
  const encoder = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signatureBuffer = await crypto.subtle.sign('HMAC', cryptoKey, encoder.encode(signedPayload));
  return Array.from(new Uint8Array(signatureBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

describe('verifyStripeSignature — Stripe署名検証', () => {
  const secret = 'whsec_test_secret_key';
  const validPayload = JSON.stringify({ id: 'evt_test', type: 'test.event', data: { object: {} } });

  it('正しい署名で検証成功', async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    const sig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    const event = await verifyStripeSignature(validPayload, header, secret);
    expect(event.id).toBe('evt_test');
    expect(event.type).toBe('test.event');
  });

  it('署名ヘッダーがnull: エラー', async () => {
    await expect(verifyStripeSignature(validPayload, null, secret))
      .rejects.toThrow('Stripe-Signatureヘッダーがありません');
  });

  it('署名ヘッダーが空文字: エラー', async () => {
    await expect(verifyStripeSignature(validPayload, '', secret))
      .rejects.toThrow('Stripe-Signatureヘッダーがありません');
  });

  it('不正な署名フォーマット（タイムスタンプなし）: エラー', async () => {
    await expect(verifyStripeSignature(validPayload, 'v1=abc123', secret))
      .rejects.toThrow('形式が不正');
  });

  it('不正な署名フォーマット（v1なし）: エラー', async () => {
    await expect(verifyStripeSignature(validPayload, 't=1234567890', secret))
      .rejects.toThrow('形式が不正');
  });

  it('不正な署名（改竄されたペイロード）: エラー', async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    const sig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    // ペイロードを改竄
    const tamperedPayload = JSON.stringify({ id: 'evt_tampered', type: 'test.event', data: { object: {} } });
    await expect(verifyStripeSignature(tamperedPayload, header, secret))
      .rejects.toThrow('署名の検証に失敗');
  });

  it('不正な署名（間違ったシークレット）: エラー', async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    const sig = await generateTestSignature(validPayload, 'wrong_secret', timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    await expect(verifyStripeSignature(validPayload, header, secret))
      .rejects.toThrow('署名の検証に失敗');
  });

  it('タイムスタンプが期限切れ（5分超過）: エラー', async () => {
    const timestamp = Math.floor(Date.now() / 1000) - 400; // 6分40秒前
    const sig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    await expect(verifyStripeSignature(validPayload, header, secret))
      .rejects.toThrow('タイムスタンプが許容範囲外');
  });

  it('タイムスタンプが未来すぎ（5分超過）: エラー', async () => {
    const timestamp = Math.floor(Date.now() / 1000) + 400; // 6分40秒後
    const sig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    await expect(verifyStripeSignature(validPayload, header, secret))
      .rejects.toThrow('タイムスタンプが許容範囲外');
  });

  it('タイムスタンプが範囲内（4分59秒前）: 検証成功', async () => {
    const timestamp = Math.floor(Date.now() / 1000) - 299; // 4分59秒前
    const sig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    const event = await verifyStripeSignature(validPayload, header, secret);
    expect(event.id).toBe('evt_test');
  });

  it('空のペイロード: JSONパースエラー', async () => {
    const emptyPayload = '';
    const timestamp = Math.floor(Date.now() / 1000);
    const sig = await generateTestSignature(emptyPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    // 空文字列はJSON.parseで失敗
    await expect(verifyStripeSignature(emptyPayload, header, secret))
      .rejects.toThrow();
  });

  it('不正なJSONペイロード: JSONパースエラー', async () => {
    const invalidPayload = '{not valid json}';
    const timestamp = Math.floor(Date.now() / 1000);
    const sig = await generateTestSignature(invalidPayload, secret, timestamp);
    const header = `t=${timestamp},v1=${sig}`;

    await expect(verifyStripeSignature(invalidPayload, header, secret))
      .rejects.toThrow();
  });

  it('複数のv1署名がある場合、1つでも正しければ成功', async () => {
    const timestamp = Math.floor(Date.now() / 1000);
    const correctSig = await generateTestSignature(validPayload, secret, timestamp);
    const header = `t=${timestamp},v1=invalid_sig_abc,v1=${correctSig}`;

    const event = await verifyStripeSignature(validPayload, header, secret);
    expect(event.id).toBe('evt_test');
  });
});
