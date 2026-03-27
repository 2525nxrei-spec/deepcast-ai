/**
 * Stripe署名検証 (verifyStripeSignature) — 第2ラウンド異常系テスト
 * リプレイ攻撃境界値、巨大ペイロード、特殊文字、フォーマット攻撃
 */
import { describe, it, expect } from 'vitest';
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

describe('verifyStripeSignature — R2異常系', () => {
  const secret = 'whsec_test_secret_key';
  const validPayload = JSON.stringify({ id: 'evt_r2', type: 'test.event', data: { object: {} } });

  describe('タイムスタンプ境界値テスト', () => {
    it('ちょうど300秒（5分）前: 検証成功', async () => {
      const timestamp = Math.floor(Date.now() / 1000) - 300;
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(validPayload, header, secret);
      expect(event.id).toBe('evt_r2');
    });

    it('301秒前: エラー（許容範囲外）', async () => {
      const timestamp = Math.floor(Date.now() / 1000) - 301;
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('タイムスタンプが許容範囲外');
    });

    it('ちょうど300秒（5分）未来: 検証成功', async () => {
      const timestamp = Math.floor(Date.now() / 1000) + 300;
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(validPayload, header, secret);
      expect(event.id).toBe('evt_r2');
    });

    it('301秒未来: エラー（許容範囲外）', async () => {
      const timestamp = Math.floor(Date.now() / 1000) + 301;
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('タイムスタンプが許容範囲外');
    });

    it('タイムスタンプ=0: エラー（falsyで形式不正扱い）', async () => {
      const sig = await generateTestSignature(validPayload, secret, 0);
      const header = `t=0,v1=${sig}`;
      // timestamp=0はfalsyのため、!timestamp判定で形式不正エラーになる
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('形式が不正');
    });

    it('負のタイムスタンプ: エラー', async () => {
      const sig = await generateTestSignature(validPayload, secret, -100);
      const header = `t=-100,v1=${sig}`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('タイムスタンプが許容範囲外');
    });
  });

  describe('署名ヘッダーフォーマット攻撃', () => {
    it('ヘッダーにundefined文字列: エラー', async () => {
      await expect(verifyStripeSignature(validPayload, 'undefined', secret))
        .rejects.toThrow();
    });

    it('ヘッダーにカンマのみ: エラー', async () => {
      await expect(verifyStripeSignature(validPayload, ',,,', secret))
        .rejects.toThrow('形式が不正');
    });

    it('ヘッダーにt=のみ（v1なし）: エラー', async () => {
      await expect(verifyStripeSignature(validPayload, 't=12345', secret))
        .rejects.toThrow('形式が不正');
    });

    it('ヘッダーにv1=のみ（tなし）: エラー', async () => {
      await expect(verifyStripeSignature(validPayload, 'v1=abc123', secret))
        .rejects.toThrow('形式が不正');
    });

    it('t=NaN: エラー（タイムスタンプ不正）', async () => {
      await expect(verifyStripeSignature(validPayload, 't=NaN,v1=abc', secret))
        .rejects.toThrow();
    });

    it('空白を含むヘッダー: 署名不一致でエラー', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t = ${timestamp}, v1 = ${sig}`;
      // スペースがあるとパースが壊れる
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow();
    });

    it('v1が空文字: 署名不一致', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const header = `t=${timestamp},v1=`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('署名の検証に失敗');
    });
  });

  describe('特殊ペイロード', () => {
    it('日本語を含むペイロード: 正しい署名で成功', async () => {
      const jpPayload = JSON.stringify({ id: 'evt_jp', type: 'test', data: { message: 'テスト日本語' } });
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(jpPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(jpPayload, header, secret);
      expect(event.data.message).toBe('テスト日本語');
    });

    it('絵文字を含むペイロード: 正しい署名で成功', async () => {
      const emojiPayload = JSON.stringify({ id: 'evt_emoji', type: 'test', data: { emoji: '🎉🔥' } });
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(emojiPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(emojiPayload, header, secret);
      expect(event.data.emoji).toBe('🎉🔥');
    });

    it('大きなペイロード（10KB）: 正しい署名で成功', async () => {
      const bigData = { id: 'evt_big', type: 'test', data: { large: 'x'.repeat(10000) } };
      const bigPayload = JSON.stringify(bigData);
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(bigPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(bigPayload, header, secret);
      expect(event.id).toBe('evt_big');
    });

    it('ネストの深いJSON: 正しい署名で成功', async () => {
      const nested = { id: 'evt_nest', type: 'test', data: { a: { b: { c: { d: { e: 'deep' } } } } } };
      const nestedPayload = JSON.stringify(nested);
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(nestedPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      const event = await verifyStripeSignature(nestedPayload, header, secret);
      expect(event.data.a.b.c.d.e).toBe('deep');
    });
  });

  describe('シークレット異常系', () => {
    it('空のシークレット: エラー（Zero-length key）', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      // crypto.subtle.importKeyが空キーを拒否するため、署名検証まで到達しない
      await expect(verifyStripeSignature(validPayload, header, ''))
        .rejects.toThrow();
    });

    it('非常に長いシークレット: 署名不一致', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const sig = await generateTestSignature(validPayload, secret, timestamp);
      const header = `t=${timestamp},v1=${sig}`;
      await expect(verifyStripeSignature(validPayload, header, 'x'.repeat(1000)))
        .rejects.toThrow('署名の検証に失敗');
    });
  });

  describe('全署名が不正な場合', () => {
    it('複数の不正なv1署名: 全て失敗', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const header = `t=${timestamp},v1=aaa,v1=bbb,v1=ccc`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('署名の検証に失敗');
    });

    it('v1署名の長さが不一致（短すぎ）: 失敗', async () => {
      const timestamp = Math.floor(Date.now() / 1000);
      const header = `t=${timestamp},v1=abc`;
      await expect(verifyStripeSignature(validPayload, header, secret))
        .rejects.toThrow('署名の検証に失敗');
    });
  });
});
