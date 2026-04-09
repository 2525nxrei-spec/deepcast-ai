/**
 * 音声保護テスト — GET /api/audio/[episode]
 * Pro音声の認証ガード、Freeエピソードの公開アクセス確認
 * tier判定はepisodes.json（Single Source of Truth）から動的に取得
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { createTestEnv, createTestUser, createContext, parseResponse } from './helpers.js';
import { onRequestGet as audioHandler, _resetEpisodesCache } from '../functions/api/audio/[episode].js';

let mf, db, r2, env;

beforeAll(async () => {
  ({ mf, db, r2, env } = await createTestEnv());

  // R2にテスト用音声ファイルをアップロード
  // tier判定はepisodes.jsonから動的取得（ハードコードなし）
  const fakeAudio = new Uint8Array([0xFF, 0xFB, 0x90, 0x00]); // 最小限のMP3ヘッダー
  await r2.put('episodes/ep001.mp3', fakeAudio);
  await r2.put('episodes/ep002.mp3', fakeAudio);
  await r2.put('episodes/ep004.mp3', fakeAudio);
  await r2.put('episodes/ep005.mp3', fakeAudio);
});

afterAll(async () => {
  await mf.dispose();
});

beforeEach(async () => {
  await db.exec('DELETE FROM users');
  // テスト間でepisodes.jsonのキャッシュをリセット
  _resetEpisodesCache();
});

describe('GET /api/audio/[episode]', () => {
  // --- Freeエピソード（episodes.jsonでtier:"free"のもの） ---

  it('Freeエピソード — 認証なしでアクセス可能', async () => {
    const request = new Request('https://deepcast-ai.com/api/audio/ep002', {
      method: 'GET',
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep002' } }));

    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('audio/mpeg');
  });

  it('Freeエピソード — Freeユーザーでもアクセス可能', async () => {
    const user = await createTestUser(db, { email: 'free@example.com', plan: 'free' });

    const request = new Request('https://deepcast-ai.com/api/audio/ep004', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep004' } }));

    expect(res.status).toBe(200);
  });

  // --- Proエピソード（episodes.jsonでtier:"pro"のもの: ep001, ep006, ep007） ---

  it('Proエピソード + Proユーザー — アクセス可能', async () => {
    const user = await createTestUser(db, { email: 'pro@example.com', plan: 'pro' });

    const request = new Request('https://deepcast-ai.com/api/audio/ep001', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep001' } }));

    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('audio/mpeg');
  });

  it('Proエピソード + Freeユーザー — 403で拒否', async () => {
    const user = await createTestUser(db, { email: 'free-blocked@example.com', plan: 'free' });

    const request = new Request('https://deepcast-ai.com/api/audio/ep001', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep001' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(403);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('Proプラン限定');
  });

  it('Proエピソード + 未認証 — 401で拒否', async () => {
    const request = new Request('https://deepcast-ai.com/api/audio/ep001', {
      method: 'GET',
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep001' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(401);
    expect(body.ok).toBe(false);
    expect(body.error).toContain('認証が必要');
  });

  // --- バリデーション ---

  it('不正なエピソードID形式 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/audio/../../etc/passwd', {
      method: 'GET',
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: '../../etc/passwd' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
    expect(body.error).toContain('無効なエピソードID');
  });

  it('存在しないエピソード — 404を返す', async () => {
    const user = await createTestUser(db, { email: 'notfound@example.com', plan: 'pro' });

    const request = new Request('https://deepcast-ai.com/api/audio/ep999', {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${user.token}` },
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: 'ep999' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(404);
    expect(body.error).toContain('見つかりません');
  });

  it('エピソードID未指定 — 400を返す', async () => {
    const request = new Request('https://deepcast-ai.com/api/audio/', {
      method: 'GET',
    });

    const res = await audioHandler(createContext(request, env, { params: { episode: '' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(400);
  });

  it('AUDIO_BUCKET未設定 — 500を返す（Freeエピソード）', async () => {
    const envNoBucket = { ...env, AUDIO_BUCKET: null };

    const request = new Request('https://deepcast-ai.com/api/audio/ep002', {
      method: 'GET',
    });

    const res = await audioHandler(createContext(request, envNoBucket, { params: { episode: 'ep002' } }));
    const { status, body } = await parseResponse(res);

    expect(status).toBe(500);
    expect(body.error).toContain('音声ストレージ');
  });
});
