/**
 * functions/_middleware.js のテスト
 * CORS、セキュリティヘッダー、レート制限の検証
 */
import { describe, it, expect } from 'vitest';
import { onRequest } from '../functions/_middleware.js';

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

describe('_middleware.js — グローバルミドルウェア', () => {
  describe('CORS', () => {
    it('OPTIONSリクエスト: 204 + CORSヘッダー', async () => {
      const ctx = createContext('OPTIONS', 'https://deepcast-ai.com/api/auth/login', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.status).toBe(204);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
      expect(res.headers.get('Access-Control-Allow-Methods')).toContain('GET');
    });

    it('許可されたオリジン: そのオリジンがAccess-Control-Allow-Originに設定', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'http://localhost:8788',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('http://localhost:8788');
    });

    it('許可されていないオリジン: デフォルトオリジンが設定', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'https://evil.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    });
  });

  describe('セキュリティヘッダー', () => {
    it('X-Content-Type-Options, X-Frame-Options等が付与される', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
      expect(res.headers.get('X-Frame-Options')).toBe('DENY');
      expect(res.headers.get('X-XSS-Protection')).toBe('1; mode=block');
      expect(res.headers.get('Strict-Transport-Security')).toContain('max-age');
    });
  });

  describe('Webhook例外', () => {
    it('Webhookパスは CORSヘッダーなし（セキュリティヘッダーのみ）', async () => {
      const ctx = createContext('POST', 'https://deepcast-ai.com/api/stripe/webhook', {});
      const res = await onRequest(ctx);
      // CORSヘッダーがない（Stripeから直接呼ばれるため）
      expect(res.headers.get('Access-Control-Allow-Origin')).toBeNull();
      // セキュリティヘッダーはある
      expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
    });
  });
});
