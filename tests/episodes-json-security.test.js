/**
 * episodes.jsonセキュリティテスト
 * - 音声URLが含まれないことを確認（直リンク防止）
 * - audioIdフィールドが存在することを確認
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('episodes.json セキュリティ', () => {
  const episodesPath = resolve(__dirname, '../episodes/episodes.json');
  const episodes = JSON.parse(readFileSync(episodesPath, 'utf-8'));

  it('音声ファイルの直接URL（audioフィールド）が含まれないこと', () => {
    episodes.forEach(ep => {
      // "audio" フィールドが存在しない、またはURL形式でないことを確認
      expect(ep).not.toHaveProperty('audio');
    });
  });

  it('全エピソードにaudioIdフィールドが存在すること', () => {
    episodes.forEach(ep => {
      expect(ep).toHaveProperty('audioId');
      expect(ep.audioId).toMatch(/^ep\d{3}$/);
    });
  });

  it('R2の直接URL（audio.deepcast-ai.com）がJSON内に含まれないこと', () => {
    const jsonStr = JSON.stringify(episodes);
    expect(jsonStr).not.toContain('audio.deepcast-ai.com');
    expect(jsonStr).not.toContain('.mp3');
  });

  it('各エピソードにtierフィールドが存在すること（サーバーサイド判定用）', () => {
    episodes.forEach(ep => {
      expect(ep).toHaveProperty('tier');
      expect(['free', 'pro']).toContain(ep.tier);
    });
  });
});
