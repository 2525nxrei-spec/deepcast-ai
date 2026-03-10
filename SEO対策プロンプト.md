# SEO対策プロンプト（Claude Code用）

新しいエピソードを追加するとき、このプロンプトを使う。

---

## 一発実行プロンプト（これをコピペして使う）

```
"G:\マイドライブ\0_deep cast" のDeepCast AIサイトに新しいエピソードを追加してSEO対策を実行して。
エージェントを並列で使って高速にやって。

■ 新エピソードの情報
- タイトル: （ここに入力）
- サブタイトル: （ここに入力）
- カテゴリ: tech / business / science / society から選択
- タグ: （カンマ区切りで入力）
- 音声ファイル: episodes/epXXX.mp3（ファイル名を入力）

■ やること

【1. エピソード記事ページの作成】
既存のエピソードページ（episodes/ep001.html など）をテンプレートにして新しいHTMLを作成。
以下を必ず含めること:
- ポッドキャストの内容を3,000字以上の記事テキストとしてHTMLに埋め込む（Google検索に引っかかるため最重要）
- 記事はh2/h3の見出し階層、段落、highlight-boxを使った読みやすい構成にする
- テーマの本質を掘り下げた解説記事として、検索ユーザーが満足する情報量にする
- SEOメタタグ一式: title（60-75字）、meta description（120-160字）、keywords
- canonical URL
- OGPメタタグ（og:title, og:description, og:image, og:url, og:type="article"）
- Twitter Cardメタタグ
- JSON-LD構造化データ（PodcastEpisode + BreadcrumbList）
- 内部リンクは href="../" を使うこと（href="../index.html" は絶対に使わない）

【2. episodes.json の更新】
新エピソードのエントリを先頭に追加。idは連番、articleとaudioのパスを正しく設定。

【3. sitemap.xml の更新】
新エピソードページのURLを追加。lastmodは今日の日付。
feed.xmlはサイトマップに入れないこと。

【4. feed.xml（RSSフィード）の更新】
新エピソードのitemを先頭に追加。既存のフォーマットに合わせる。

【5. リダイレクト対策チェック】
全HTMLファイルを検索して href="index.html" や href="../index.html" が残っていないか確認。
見つかったら href="./" や href="../" に置換。

【6. sw.js キャッシュ更新】
CACHE_NAME のバージョン番号を+1。

【7. GitHubにcommit & push】
リポジトリ: origin master
```

---

## ポッドキャスト記事コンテンツの書き方（最重要）

エピソードページのSEOで最も重要なのは、ポッドキャストの内容を**検索可能なテキスト**としてHTMLに埋め込むこと。

### 構成テンプレート

```html
<div class="article-body">
  <h2>セクション1の見出し</h2>
  <p>導入段落。テーマの背景と問題提起。</p>
  <p>詳細な解説。データや事例を交えて。</p>

  <h2>セクション2の見出し</h2>
  <p>本論。テーマの核心を掘り下げる。</p>

  <h3>サブトピック</h3>
  <p>さらに詳しい解説。</p>

  <div class="highlight-box">
    <h4>ポイントまとめ</h4>
    <ul>
      <li><strong>要点1</strong> — 説明</li>
      <li><strong>要点2</strong> — 説明</li>
      <li><strong>要点3</strong> — 説明</li>
    </ul>
  </div>

  <h2>結論</h2>
  <p>まとめと示唆。</p>
</div>
```

### ルール
- 3,000字以上（5,000字あるとなお良い）
- h2を5〜7個、h3を適宜使って階層化
- highlight-boxを2〜4個入れてスキャンしやすくする
- <strong>で重要キーワードを強調（Google検索での重み付け）
- 専門用語・固有名詞を適切に散りばめる（検索キーワードになる）
- 一般的なまとめではなく、独自の切り口や深い分析を含める

---

## 参考: 現在のファイル構成

```
episodes/
  episodes.json    ← エピソード一覧データ
  ep001.html       ← 各エピソードの記事ページ
  ep002.html
  ep003.html
  ep021.mp3        ← 音声ファイル（番号体系が違うので注意）
  ep022.mp3
  ep023.mp3
sitemap.xml
feed.xml
sw.js
```

## 注意事項
- href="index.html" は使わない（Cloudflareが301リダイレクトするためSEOに悪影響）
- feed.xml はsitemap.xmlに入れない
- OGP画像: 専用がなければ assets/cover-default.svg を使う
- AdSenseコードは記事ページには入れない（既存ページに倣う）
