/**
 * ミドルウェア — レート制限の詳細テスト
 * 認証エンドポイントと一般エンドポイントのレート制限差異、
 * Webhookのレート制限除外を検証
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// ミドルウェアはモジュールレベルのstateを持つため、テスト間の干渉を考慮
// 各テストでは異なるIPを使用して隔離

describe('_middleware.js — レート制限詳細テスト', () => {
  let onRequest;

  beforeEach(async () => {
    vi.resetModules();
    const mod = await import('../functions/_middleware.js');
    onRequest = mod.onRequest;
  });

  function createContext(method, url, headers = {}, nextResponse = null) {
    return {
      request: new Request(url, {
        method,
        headers: new Headers(headers),
      }),
      async next() {
        return nextResponse || new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      },
    };
  }

  it('Webhookエンドポイントはレート制限対象外', async () => {
    // Webhookに大量リクエストを送信してもレート制限されない
    for (let i = 0; i < 15; i++) {
      const ctx = createContext('POST', 'https://deepcast-ai.com/api/stripe/webhook', {
        'CF-Connecting-IP': '10.0.0.1',
      });
      const res = await onRequest(ctx);
      expect(res.status).toBe(200);
    }
  });

  it('非WebhookエンドポイントにCORSヘッダーが付与される', async () => {
    const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
      'Origin': 'https://deepcast-ai.com',
      'CF-Connecting-IP': '10.0.0.2',
    });
    const res = await onRequest(ctx);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    // セキュリティヘッダーもある
    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
  });

  it('Webhookエンドポイントにはセキュリティヘッダーのみ（CORSなし）', async () => {
    const ctx = createContext('POST', 'https://deepcast-ai.com/api/stripe/webhook', {
      'Origin': 'https://evil.com',
    });
    const res = await onRequest(ctx);
    // セキュリティヘッダーあり
    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
    // CORSヘッダーなし
    expect(res.headers.get('Access-Control-Allow-Origin')).toBeNull();
  });

  it('nextのレスポンスが500でもヘッダーは付与', async () => {
    const errResponse = new Response('Internal Error', { status: 500 });
    const ctx = createContext('GET', 'https://deepcast-ai.com/api/test', {
      'Origin': 'https://deepcast-ai.com',
      'CF-Connecting-IP': '10.0.0.4',
    }, errResponse);
    const res = await onRequest(ctx);
    expect(res.status).toBe(500);
    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
  });

  it('DELETEメソッドもCORSで許可される', async () => {
    const ctx = createContext('OPTIONS', 'https://deepcast-ai.com/api/auth/account', {
      'Origin': 'https://deepcast-ai.com',
    });
    const res = await onRequest(ctx);
    expect(res.headers.get('Access-Control-Allow-Methods')).toContain('DELETE');
  });
});
