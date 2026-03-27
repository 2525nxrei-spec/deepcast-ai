/**
 * _middleware.js — 高度なテスト
 * レート制限、セキュリティヘッダー詳細、エッジケース
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

describe('_middleware.js — 高度なテスト', () => {
  describe('CORS詳細', () => {
    it('www.deepcast-ai.comからのリクエスト: 許可', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'https://www.deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://www.deepcast-ai.com');
    });

    it('localhost:3000からのリクエスト: 許可', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'http://localhost:3000',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('http://localhost:3000');
    });

    it('Originヘッダーなし: デフォルトオリジンが設定', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {});
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    });

    it('OPTIONS: Access-Control-Max-Ageが設定される', async () => {
      const ctx = createContext('OPTIONS', 'https://deepcast-ai.com/api/auth/login', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Max-Age')).toBe('86400');
    });

    it('OPTIONS: Authorizationヘッダーが許可される', async () => {
      const ctx = createContext('OPTIONS', 'https://deepcast-ai.com/api/auth/login', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Access-Control-Allow-Headers')).toContain('Authorization');
    });
  });

  describe('セキュリティヘッダー詳細', () => {
    it('Referrer-Policyが設定される', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Referrer-Policy')).toBe('strict-origin-when-cross-origin');
    });

    it('Permissions-Policyが設定される', async () => {
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/auth/me', {
        Origin: 'https://deepcast-ai.com',
      });
      const res = await onRequest(ctx);
      expect(res.headers.get('Permissions-Policy')).toContain('camera=()');
      expect(res.headers.get('Permissions-Policy')).toContain('microphone=()');
    });

    it('WebhookにもX-Content-Type-Optionsが設定される', async () => {
      const ctx = createContext('POST', 'https://deepcast-ai.com/api/stripe/webhook', {});
      const res = await onRequest(ctx);
      expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
      expect(res.headers.get('X-Frame-Options')).toBe('DENY');
    });
  });

  describe('レスポンスのpassthrough', () => {
    it('nextのレスポンスステータスがそのまま返る', async () => {
      const errorResponse = new Response(JSON.stringify({ ok: false }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
      const ctx = createContext('GET', 'https://deepcast-ai.com/api/unknown', {
        Origin: 'https://deepcast-ai.com',
      }, errorResponse);
      const res = await onRequest(ctx);
      expect(res.status).toBe(404);
      // セキュリティヘッダーとCORSは付与
      expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    });
  });
});
