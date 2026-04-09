/**
 * ミドルウェアテスト — CORS / セキュリティヘッダー / レート制限
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { createTestEnv, createContext } from './helpers.js';
import { onRequest as middleware } from '../functions/_middleware.js';

let mf, env;

beforeAll(async () => {
  ({ mf, env } = await createTestEnv());
});

afterAll(async () => {
  await mf.dispose();
});

/**
 * ミドルウェアのcontextを生成
 * next() は通常のAPIレスポンスを模擬する
 */
function createMiddlewareContext(request, nextResponse) {
  return {
    request,
    next: async () => nextResponse || new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  };
}

// === CORSヘッダー ===

describe('CORS', () => {
  it('許可されたOriginにCORSヘッダーが付く', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Origin': 'https://deepcast-ai.com' },
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    expect(res.headers.get('Access-Control-Allow-Methods')).toContain('GET');
    expect(res.headers.get('Access-Control-Allow-Headers')).toContain('Authorization');
  });

  it('localhostのOriginも許可される', async () => {
    const request = new Request('http://localhost:8788/api/auth/me', {
      method: 'GET',
      headers: { 'Origin': 'http://localhost:8788' },
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('http://localhost:8788');
  });

  it('不許可のOriginにはデフォルトOriginが設定される', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Origin': 'https://evil-site.com' },
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
  });

  it('OPTIONS preflight — 204を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'OPTIONS',
      headers: { 'Origin': 'https://deepcast-ai.com' },
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.status).toBe(204);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    expect(res.headers.get('Access-Control-Max-Age')).toBe('86400');
  });

  it('Webhookパス — CORSヘッダーが付かない', async () => {
    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
      headers: { 'Origin': 'https://deepcast-ai.com' },
    });

    const res = await middleware(createMiddlewareContext(request));

    // WebhookはCORSなし（Stripe直接呼び出しのため）
    expect(res.headers.get('Access-Control-Allow-Origin')).toBeNull();
  });
});

// === セキュリティヘッダー ===

describe('セキュリティヘッダー', () => {
  it('全レスポンスにセキュリティヘッダーが付与される', async () => {
    const request = new Request('https://deepcast-ai.com/api/auth/me', {
      method: 'GET',
      headers: { 'Origin': 'https://deepcast-ai.com' },
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(res.headers.get('X-Frame-Options')).toBe('DENY');
    expect(res.headers.get('X-XSS-Protection')).toBe('1; mode=block');
    expect(res.headers.get('Referrer-Policy')).toBe('strict-origin-when-cross-origin');
    expect(res.headers.get('Strict-Transport-Security')).toContain('max-age=');
    expect(res.headers.get('Permissions-Policy')).toContain('camera=()');
  });

  it('Webhookレスポンスにもセキュリティヘッダーが付く', async () => {
    const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
      method: 'POST',
    });

    const res = await middleware(createMiddlewareContext(request));

    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(res.headers.get('X-Frame-Options')).toBe('DENY');
  });
});

// === レート制限 ===

describe('レート制限', () => {
  it('認証エンドポイントは10回/分で制限される', async () => {
    // ユニークIPを使って他テストと干渉しない
    const testIP = `rate-test-auth-${Date.now()}`;
    let lastResponse;

    for (let i = 0; i < 12; i++) {
      const request = new Request('https://deepcast-ai.com/api/auth/login', {
        method: 'POST',
        headers: {
          'CF-Connecting-IP': testIP,
          'Origin': 'https://deepcast-ai.com',
          'Content-Type': 'application/json',
        },
      });

      lastResponse = await middleware(createMiddlewareContext(request));
    }

    // 11回目以降は429が返るはず
    expect(lastResponse.status).toBe(429);
    const body = await lastResponse.json();
    expect(body.ok).toBe(false);
    expect(body.error).toContain('リクエストが多すぎます');
  });

  it('一般エンドポイントは120回/分の制限（通常はヒットしない）', async () => {
    const testIP = `rate-test-general-${Date.now()}`;

    // 5回程度では制限されない
    for (let i = 0; i < 5; i++) {
      const request = new Request('https://deepcast-ai.com/api/billing/status', {
        method: 'GET',
        headers: {
          'CF-Connecting-IP': testIP,
          'Origin': 'https://deepcast-ai.com',
        },
      });

      const res = await middleware(createMiddlewareContext(request));
      expect(res.status).not.toBe(429);
    }
  });

  it('Webhookはレート制限の対象外', async () => {
    const testIP = `rate-test-webhook-${Date.now()}`;

    for (let i = 0; i < 15; i++) {
      const request = new Request('https://deepcast-ai.com/api/stripe/webhook', {
        method: 'POST',
        headers: { 'CF-Connecting-IP': testIP },
      });

      const res = await middleware(createMiddlewareContext(request));
      // Webhookは429にならないはず
      expect(res.status).not.toBe(429);
    }
  });
});

// === エラーハンドリング ===

describe('エラーハンドリング', () => {
  it('ハンドラが例外を投げても500+CORSヘッダーが返る', async () => {
    const request = new Request('https://deepcast-ai.com/api/test-error', {
      method: 'GET',
      headers: { 'Origin': 'https://deepcast-ai.com' },
    });

    const context = {
      request,
      next: async () => { throw new Error('Unexpected error'); },
    };

    const res = await middleware(context);

    expect(res.status).toBe(500);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('https://deepcast-ai.com');
    expect(res.headers.get('X-Content-Type-Options')).toBe('nosniff');
  });
});
