/**
 * テストヘルパー — Miniflare D1 + モックenv生成
 * 各テストファイルで共通利用する
 */

import { Miniflare } from 'miniflare';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createJWT, hashPassword, generateSalt, generateId } from '../functions/lib/crypto.js';

const SCHEMA_PATH = resolve(import.meta.dirname, '..', 'schema.sql');
const JWT_SECRET = 'test-jwt-secret-for-deepcast';

/**
 * Miniflareインスタンスを起動しD1スキーマを適用
 * @returns {{ mf: Miniflare, db: D1Database, env: object }}
 */
export async function createTestEnv() {
  const mf = new Miniflare({
    modules: true,
    script: 'export default { async fetch() { return new Response("ok"); } }',
    d1Databases: ['DB'],
    r2Buckets: ['AUDIO_BUCKET'],
  });

  const db = await mf.getD1Database('DB');
  const r2 = await mf.getR2Bucket('AUDIO_BUCKET');

  // スキーマ適用（D1のexecは複数行SQLを正しくパースできないため、prepare().run()で個別実行）
  const rawSchema = readFileSync(SCHEMA_PATH, 'utf-8');
  const statements = rawSchema
    .replace(/--.*$/gm, '')
    .split(';')
    .map(s => s.trim())
    .filter(s => s.length > 0);
  for (const stmt of statements) {
    await db.prepare(stmt).run();
  }

  // テスト用エピソードデータ（固定）
  // 本番のepisodes.jsonとは独立させ、準備中状態でもテストが安定動作するようにする
  const testEpisodes = [
    { "id": 1, "title": "テストエピソード1", "tier": "pro", "audio": "episodes/ep001.mp3" },
    { "id": 2, "title": "テストエピソード2", "tier": "free", "audio": "episodes/ep002.mp3" },
    { "id": 3, "title": "テストエピソード3", "tier": "free", "audio": "episodes/ep003.mp3" },
    { "id": 4, "title": "テストエピソード4", "tier": "free", "audio": "episodes/ep004.mp3" },
    { "id": 5, "title": "テストエピソード5", "tier": "free", "audio": "episodes/ep005.mp3" },
    { "id": 6, "title": "テストエピソード6", "tier": "pro", "audio": "episodes/ep006.mp3" },
    { "id": 7, "title": "テストエピソード7", "tier": "pro", "audio": "episodes/ep007.mp3" }
  ];
  const episodesJson = JSON.stringify(testEpisodes);
  const ASSETS = {
    fetch: async () => new Response(episodesJson, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  };

  const env = {
    DB: db,
    AUDIO_BUCKET: r2,
    ASSETS,
    JWT_SECRET,
    STRIPE_SECRET_KEY: 'sk_test_fake_key',
    STRIPE_WEBHOOK_SECRET: 'whsec_test_secret',
    STRIPE_PRICE_PRO: 'price_test_pro_123',
    FRONTEND_URL: 'https://deepcast-ai.com',
  };

  return { mf, db, r2, env };
}

/**
 * テスト用ユーザーをDBに挿入
 * @returns {{ id, email, password, token, salt, hash }}
 */
export async function createTestUser(db, overrides = {}) {
  const id = overrides.id || generateId();
  const email = overrides.email || `test-${Date.now()}@example.com`;
  const password = overrides.password || 'TestPass123';
  const plan = overrides.plan || 'free';
  const displayName = overrides.display_name || 'テストユーザー';
  const salt = generateSalt();
  const hash = await hashPassword(password, salt);

  await db.prepare(
    `INSERT INTO users (id, email, password_hash, password_salt, display_name, plan, stripe_customer_id, stripe_subscription_id)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id, email, hash, salt, displayName, plan,
    overrides.stripe_customer_id || null,
    overrides.stripe_subscription_id || null,
  ).run();

  // JWT発行
  const token = await createJWT(
    { sub: id, email, plan, exp: Math.floor(Date.now() / 1000) + 86400 },
    JWT_SECRET,
  );

  return { id, email, password, plan, displayName, salt, hash, token };
}

/**
 * 期限切れJWTを生成
 */
export async function createExpiredToken(userId, email) {
  return createJWT(
    { sub: userId, email, plan: 'free', exp: Math.floor(Date.now() / 1000) - 3600 },
    JWT_SECRET,
  );
}

/**
 * Pages Functions の context オブジェクトを生成
 */
export function createContext(request, env, overrides = {}) {
  return {
    request,
    env,
    params: overrides.params || {},
    next: overrides.next || (async () => new Response('Not Found', { status: 404 })),
  };
}

/**
 * JSONレスポンスをパース
 */
export async function parseResponse(response) {
  const body = await response.json();
  return { status: response.status, body, headers: response.headers };
}

export { JWT_SECRET };
