/**
 * functions/lib/response.js のテスト
 */
import { describe, it, expect } from 'vitest';
import { errorResponse, jsonResponse } from '../functions/lib/response.js';

describe('lib/response.js — レスポンスユーティリティ', () => {
  it('errorResponse: デフォルトは400', async () => {
    const res = errorResponse('テストエラー');
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(json.error).toBe('テストエラー');
  });

  it('errorResponse: カスタムステータスコード', async () => {
    const res = errorResponse('認証エラー', 401);
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(json.error).toBe('認証エラー');
  });

  it('errorResponse: Content-Typeヘッダー', () => {
    const res = errorResponse('err');
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
  });

  it('jsonResponse: デフォルトは200', async () => {
    const res = jsonResponse({ user: { id: '1' } });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(json.user.id).toBe('1');
  });

  it('jsonResponse: カスタムステータスコード', async () => {
    const res = jsonResponse({ token: 'abc' }, 201);
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(json.token).toBe('abc');
  });
});
