/**
 * GET /api/audio/:episode — 認証付き音声ストリーミング配信
 * JWT認証を検証し、プラン権限をサーバーサイドで確認
 * FreeユーザーはFreeエピソードのみ、Proユーザーはすべてのエピソードにアクセス可能
 * 音声はR2バケットから取得してストリーミング返却
 *
 * tier判定はepisodes.jsonをSingle Source of Truthとして参照する
 */

import { errorResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';

// episodes.jsonのキャッシュ（リクエストごとにfetchしない）
let episodesCache = null;
let episodesCacheTime = 0;
const CACHE_TTL_MS = 60 * 1000; // 60秒キャッシュ

/**
 * episodes.jsonからエピソードのtierを取得する
 * episodes.jsonに該当エピソードがない or tierが未指定の場合はpro扱い（安全側に倒す）
 */
async function getEpisodeTier(episodeId, env) {
  const episodes = await loadEpisodes(env);
  const baseId = episodeId.replace(/\.mp3$/, '');
  const num = parseInt(baseId.replace('ep', ''), 10);
  if (isNaN(num)) return 'pro'; // 不明なIDはpro扱い（安全側に倒す）

  const episode = episodes.find(ep => ep.id === num);
  if (!episode || !episode.tier) return 'pro'; // 未登録・tier未指定はpro扱い（安全側に倒す）
  return episode.tier;
}

/**
 * episodes.jsonを読み込む（キャッシュ付き）
 * Cloudflare Pages Functions: env.ASSETS.fetch()で静的ファイルを取得
 * フォールバック: FRONTEND_URLからfetch
 */
async function loadEpisodes(env) {
  const now = Date.now();
  if (episodesCache && (now - episodesCacheTime) < CACHE_TTL_MS) {
    return episodesCache;
  }

  try {
    let response;
    if (env.ASSETS && typeof env.ASSETS.fetch === 'function') {
      // Cloudflare Pages Functions の ASSETS バインディング
      response = await env.ASSETS.fetch(new Request('https://dummy/episodes/episodes.json'));
    } else {
      // フォールバック: FRONTEND_URLから取得
      const baseUrl = env.FRONTEND_URL || 'https://deepcast-ai.com';
      response = await fetch(`${baseUrl}/episodes/episodes.json`);
    }

    if (!response.ok) {
      console.error('episodes.json取得失敗:', response.status);
      return episodesCache || []; // 前回のキャッシュがあればそれを返す
    }

    episodesCache = await response.json();
    episodesCacheTime = now;
    return episodesCache;
  } catch (err) {
    console.error('episodes.json読み込みエラー:', err.message);
    return episodesCache || []; // 前回のキャッシュがあればそれを返す
  }
}

/**
 * テスト用: キャッシュをリセットする
 */
export function _resetEpisodesCache() {
  episodesCache = null;
  episodesCacheTime = 0;
}

export async function onRequestGet(context) {
  const { request, env, params } = context;

  try {
    const episodeParam = params.episode;
    if (!episodeParam) {
      return errorResponse('エピソードIDが指定されていません', 400);
    }

    // ファイル名のサニタイズ（パストラバーサル防止）
    // エピソードIDはep001〜ep999の形式のみ許可
    const episodeId = episodeParam.replace(/\.mp3$/, '');
    if (!episodeId || !/^ep\d{3}$/.test(episodeId)) {
      return errorResponse('無効なエピソードIDです', 400);
    }

    const tier = await getEpisodeTier(episodeId, env);

    // Proエピソードは認証必須
    if (tier === 'pro') {
      const user = await authenticateUser(request, env);
      if (!user) {
        return errorResponse('Pro音声の再生には認証が必要です', 401);
      }
      if (user.plan !== 'pro') {
        return errorResponse('このエピソードはProプラン限定です', 403);
      }
    }

    // R2バケットから音声ファイルを取得
    const r2Key = `episodes/${episodeId}.mp3`;

    if (!env.AUDIO_BUCKET) {
      return errorResponse('音声ストレージが設定されていません', 500);
    }

    const object = await env.AUDIO_BUCKET.get(r2Key);
    if (!object) {
      return errorResponse('エピソードが見つかりません', 404);
    }

    // Range リクエスト対応（シーク用）
    const rangeHeader = request.headers.get('Range');
    const headers = {
      'Content-Type': 'audio/mpeg',
      'Cache-Control': 'private, max-age=3600',
      'Accept-Ranges': 'bytes',
    };

    if (rangeHeader && object.size) {
      const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
      if (match) {
        const start = parseInt(match[1], 10);
        const end = match[2] ? parseInt(match[2], 10) : object.size - 1;
        headers['Content-Range'] = `bytes ${start}-${end}/${object.size}`;
        headers['Content-Length'] = String(end - start + 1);

        // R2のgetでrangeオプションを使用
        const rangeObject = await env.AUDIO_BUCKET.get(r2Key, {
          range: { offset: start, length: end - start + 1 },
        });
        if (!rangeObject) {
          return errorResponse('Range取得に失敗しました', 500);
        }
        return new Response(rangeObject.body, { status: 206, headers });
      }
    }

    if (object.size) {
      headers['Content-Length'] = String(object.size);
    }

    return new Response(object.body, { status: 200, headers });
  } catch (err) {
    console.error('音声配信エラー:', err.message);
    return errorResponse('音声の取得に失敗しました', 500);
  }
}
