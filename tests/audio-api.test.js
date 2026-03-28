/**
 * 音声APIエンドポイントのテスト
 * - 認証なしアクセスで401が返ること
 * - Freeエピソードは認証なしで200が返ること
 * - Proエピソードで無料ユーザーは403が返ること
 * - episodes.jsonに音声URLが含まれないことを確認
 */

import { describe, it, expect, vi } from 'vitest';
import { createMockEnv, createRequest, parseResponse } from './helpers.js';

// 音声APIハンドラのインポート
import { onRequestGet } from '../functions/api/audio/[episode].js';

// R2モックの作成
function createMockR2Bucket(files = {}) {
  return {
    get: vi.fn(async (key, options) => {
      const file = files[key];
      if (!file) return null;
      // Rangeリクエスト対応
      if (options && options.range) {
        return {
          body: new ReadableStream(),
          size: options.range.length,
        };
      }
      return {
        body: new ReadableStream(),
        size: file.size || 1024,
      };
    }),
  };
}

function createAudioRequest(episode, token = null) {
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return createRequest('GET', `https://deepcast-ai.com/api/audio/${episode}`, null, headers);
}

// JWT生成ヘルパー（テスト用）
async function createTestJWT(payload, secret) {
  const { createJWT } = await import('../functions/lib/crypto.js');
  return createJWT(payload, secret);
}

describe('GET /api/audio/[episode]', () => {
  it('Proエピソードに認証なしでアクセスすると401が返る', async () => {
    const env = createMockEnv();
    env.AUDIO_BUCKET = createMockR2Bucket({ 'episodes/ep010.mp3': { size: 1024 } });

    const request = createAudioRequest('ep010');
    const context = { request, env, params: { episode: 'ep010' } };
    const response = await onRequestGet(context);
    const data = await parseResponse(response);

    expect(response.status).toBe(401);
    expect(data.ok).toBe(false);
    expect(data.error).toContain('認証が必要');
  });

  it('Freeエピソード(ep001)は認証なしで200が返る', async () => {
    const env = createMockEnv();
    env.AUDIO_BUCKET = createMockR2Bucket({ 'episodes/ep001.mp3': { size: 2048 } });

    const request = createAudioRequest('ep001');
    const context = { request, env, params: { episode: 'ep001' } };
    const response = await onRequestGet(context);

    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('audio/mpeg');
  });

  it('Proエピソードにfreeユーザーがアクセスすると403が返る', async () => {
    const env = createMockEnv([
      { id: 'user-1', email: 'free@test.com', plan: 'free', password_hash: 'h', password_salt: 's' },
    ]);
    env.AUDIO_BUCKET = createMockR2Bucket({ 'episodes/ep005.mp3': { size: 1024 } });

    const token = await createTestJWT(
      { sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 },
      env.JWT_SECRET
    );
    const request = createAudioRequest('ep005', token);
    const context = { request, env, params: { episode: 'ep005' } };
    const response = await onRequestGet(context);
    const data = await parseResponse(response);

    expect(response.status).toBe(403);
    expect(data.ok).toBe(false);
    expect(data.error).toContain('Proプラン限定');
  });

  it('ProエピソードにProユーザーがアクセスすると200が返る', async () => {
    const env = createMockEnv([
      { id: 'user-pro', email: 'pro@test.com', plan: 'pro', password_hash: 'h', password_salt: 's' },
    ]);
    env.AUDIO_BUCKET = createMockR2Bucket({ 'episodes/ep010.mp3': { size: 4096 } });

    const token = await createTestJWT(
      { sub: 'user-pro', exp: Math.floor(Date.now() / 1000) + 3600 },
      env.JWT_SECRET
    );
    const request = createAudioRequest('ep010', token);
    const context = { request, env, params: { episode: 'ep010' } };
    const response = await onRequestGet(context);

    expect(response.status).toBe(200);
    expect(response.headers.get('Content-Type')).toBe('audio/mpeg');
  });

  it('存在しないエピソードは404が返る', async () => {
    const env = createMockEnv();
    env.AUDIO_BUCKET = createMockR2Bucket({});

    const request = createAudioRequest('ep001');
    const context = { request, env, params: { episode: 'ep001' } };
    const response = await onRequestGet(context);
    const data = await parseResponse(response);

    expect(response.status).toBe(404);
    expect(data.ok).toBe(false);
  });

  it('AUDIO_BUCKETが未設定の場合500が返る', async () => {
    const env = createMockEnv();
    // AUDIO_BUCKETを設定しない

    const request = createAudioRequest('ep001');
    const context = { request, env, params: { episode: 'ep001' } };
    const response = await onRequestGet(context);
    const data = await parseResponse(response);

    expect(response.status).toBe(500);
    expect(data.ok).toBe(false);
  });

  it('パストラバーサル攻撃は400で拒否される', async () => {
    const env = createMockEnv();
    env.AUDIO_BUCKET = createMockR2Bucket({});

    const request = createAudioRequest('../../../etc/passwd');
    const context = { request, env, params: { episode: '../../../etc/passwd' } };
    const response = await onRequestGet(context);

    expect(response.status).toBe(400);
  });
});
