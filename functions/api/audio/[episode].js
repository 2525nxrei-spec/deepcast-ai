/**
 * GET /api/audio/:episode — 認証付き音声ストリーミング配信
 * JWT認証を検証し、プラン権限をサーバーサイドで確認
 * FreeユーザーはFreeエピソードのみ、Proユーザーはすべてのエピソードにアクセス可能
 * 音声はR2バケットから取得してストリーミング返却
 */

import { errorResponse } from '../../lib/response.js';
import { authenticateUser } from '../../lib/auth.js';

// エピソードのティア定義（episodes.jsonと同期必須）
// Freeエピソードのホワイトリスト（ここに含まれるもののみfree、それ以外は全てpro扱い）
// 安全側設計: リストに漏れがあってもpro扱いになるため、無料ユーザーに有料コンテンツが漏れない
const FREE_EPISODES = new Set([1, 2, 3, 8, 9, 10]);

function getEpisodeTier(episodeId) {
  const baseId = episodeId.replace(/\.mp3$/, '');
  const num = parseInt(baseId.replace('ep', ''), 10);
  if (isNaN(num)) return 'pro'; // 不明なIDはpro扱い（安全側に倒す）
  return FREE_EPISODES.has(num) ? 'free' : 'pro';
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

    const tier = getEpisodeTier(episodeId);

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
