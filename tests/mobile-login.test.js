/**
 * モバイルビューポートテスト
 * - CSSでモバイルメニュー展開時にnav-actionsが表示されること
 * - style.cssにモバイルメニュー対応のルールが存在すること
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('モバイルログインボタン表示', () => {
  const cssPath = resolve(__dirname, '../css/style.css');
  const cssContent = readFileSync(cssPath, 'utf-8');

  it('CSSにモバイルメニュー展開時のnav-actions表示ルールが存在すること', () => {
    // .nav-actions.active のルールが定義されていること
    expect(cssContent).toContain('.nav-actions.active');
  });

  it('ハンバーガーメニュー展開時にnav-actionsにactiveクラスが付与されるJSが存在すること', () => {
    const jsPath = resolve(__dirname, '../js/page-init.js');
    const jsContent = readFileSync(jsPath, 'utf-8');
    // navActions.classList.toggle('active') の存在確認
    expect(jsContent).toContain("navActions.classList.toggle('active')");
  });

  it('768px以下のメディアクエリ内でnav-actionsがdisplay:noneに設定されていること（デフォルト非表示）', () => {
    // @media (max-width: 768px) 内で .nav-actions { display: none; } が存在
    const mediaMatch = cssContent.match(/@media\s*\(max-width:\s*768px\)[\s\S]*?\{([\s\S]*?)(?=@media|\s*$)/);
    expect(mediaMatch).toBeTruthy();
    expect(mediaMatch[1]).toContain('.nav-actions { display: none; }');
  });

  it('HTMLのnavbarにnav-actionsセクションが含まれていること', () => {
    const indexPath = resolve(__dirname, '../index.html');
    const htmlContent = readFileSync(indexPath, 'utf-8');
    expect(htmlContent).toContain('nav-actions');
    expect(htmlContent).toContain('hamburger');
  });
});
