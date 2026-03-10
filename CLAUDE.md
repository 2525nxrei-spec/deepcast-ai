# DeepCast AI プロジェクト設定

## 基本情報
- サイト: https://deepcast-ai.com/
- ホスティング: Cloudflare Pages（GitHub連携で自動デプロイ）
- リポジトリ: https://github.com/2525nxrei-spec/deepcast-ai.git / master
- 日本語サイト

## ファイル構成
```
index.html          トップページ
all-episodes.html   エピソード一覧
episodes/
  episodes.json     エピソード一覧データ（新しい順）
  ep001.html        各エピソードの記事ページ
  ep0XX.mp3         音声ファイル（HTML番号と異なる場合あり）
feed.xml            RSSフィード（Apple Podcasts等向け）
sitemap.xml
sw.js               Service Worker
about.html / contact.html / privacy.html / terms.html / tokushoho.html / copyright.html
```

## 絶対に守るルール

### リンク
- `href="index.html"` は絶対に使わない。`href="./"` を使う
- `href="../index.html"` は絶対に使わない。`href="../"` を使う
- 理由: Cloudflare Pagesが /index.html を / に301リダイレクトするため、SEOに悪影響

### サイトマップ
- feed.xml はsitemap.xmlに入れない（RSSフィードはサイトマップ不要）

### AdSense
- アドセンス広告のコードは既にあるページにのみ存在。新規追加しない

## 新エピソード追加時のSEO対策手順

「新エピソード追加して」や「SEO対策して」と言われたら以下を全て実行:

### 1. エピソード記事ページ作成（最重要）
既存のエピソードHTML（episodes/ep001.htmlなど）をテンプレートにして作成。
**ポッドキャストの内容を3,000字以上の記事テキストとしてHTMLに埋め込む**（Google検索にかかるため最重要）。

必須要素:
- `<title>` 60-75字、「タイトル｜DeepCast AI」形式
- `<meta name="description">` 120-160字
- `<meta name="keywords">`
- `<link rel="canonical">` 正規URL
- OGPメタタグ一式（og:title, og:description, og:image, og:url, og:type="article"）
- Twitter Cardメタタグ一式
- JSON-LD構造化データ: PodcastEpisode + BreadcrumbList を配列で
- 本文: h2を5-7個、h3適宜、highlight-box 2-4個、strong でキーワード強調
- 内部リンクは `href="../"` を使用（`href="../index.html"` 禁止）

記事テンプレート:
```html
<div class="article-body">
  <h2>見出し</h2>
  <p>段落テキスト。<strong>重要キーワード</strong>を強調。</p>
  <h3>サブ見出し</h3>
  <p>詳細解説。</p>
  <div class="highlight-box">
    <h4>ポイント</h4>
    <ul>
      <li><strong>要点</strong> — 説明</li>
    </ul>
  </div>
  <h2>結論</h2>
  <p>まとめ。</p>
</div>
```

BreadcrumbList のフォーマット:
```json
{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
  {"@type":"ListItem","position":1,"name":"DeepCast AI","item":"https://deepcast-ai.com/"},
  {"@type":"ListItem","position":2,"name":"エピソード一覧","item":"https://deepcast-ai.com/all-episodes.html"},
  {"@type":"ListItem","position":3,"name":"#番号 タイトル"}
]}
```

### 2. episodes.json 更新
新エピソードを配列の先頭に追加。idは連番。

### 3. sitemap.xml 更新
新ページURL追加。lastmodは当日日付。

### 4. feed.xml 更新
新エピソードのitemを先頭に追加。既存フォーマットに合わせる。

### 5. リダイレクトチェック
全HTMLで `href=".*index\.html` を検索し、あれば修正。

### 6. sw.js キャッシュ更新
CACHE_NAME のバージョン番号を+1。

### 7. commit & push
```
git add -A && git commit && git push origin master
```

## SEO定期チェック（「SEOチェックして」と言われたら）
1. 全HTMLの index.html リンク残存チェック
2. episodes.json と sitemap.xml の整合性チェック
3. episodes.json と feed.xml の整合性チェック
4. 全ページの BreadcrumbList 構造化データ有無チェック
5. 全エピソードページの本文テキスト量チェック（3,000字以上か）
