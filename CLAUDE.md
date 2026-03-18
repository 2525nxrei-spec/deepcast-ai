# DeepCast AI プロジェクト — 完全引き継ぎドキュメント

> このファイルを読めば、プロジェクトの全貌と作業手順がわかる。
> 毎回チャットで説明し直す必要なし。

---

## クイックスタート（よくある指示と対応）

| ユーザーの指示 | やること |
|---|---|
| 「新エピソード追加して」 | → [新エピソード追加手順](#新エピソード追加手順全7ステップ) を全て実行 |
| 「SEOチェックして」 | → [SEO定期チェック](#seo定期チェック) を実行 |
| 「エピソード量産して」 | → `cd engine && python main.py pipeline` で生成〜公開まで一括実行 |
| 「push して」 | → `git add -A && git commit && git push origin master` |
| 「サイト確認して」 | → https://deepcast-ai.com/ を確認 |

---

## 基本情報

- **サイト**: https://deepcast-ai.com/
- **ホスティング**: Cloudflare Pages（GitHub連携で自動デプロイ。pushすれば反映される）
- **リポジトリ**: https://github.com/2525nxrei-spec/deepcast-ai.git / master
- **言語**: 日本語サイト
- **コンセプト**: Google Gemini AI でポッドキャスト台本+音声を自動生成 → 完全無料・登録不要で配信
- **技術スタック**: Vanilla HTML/CSS/JS（フレームワークなし）、SPA + PWA、Python（制作パイプライン）

---

## 現在の状態（2026-03-18時点）

### エピソード状況
- **旧エピソード（ep001-003）は削除済み**
- 現在の公開エピソード: ep001, ep002
- pipeline生成中: #13〜#16

### engine/ — 自動生成システム
`engine/` ディレクトリがエピソード自動生成・公開の中核システムとして稼働中。

| 項目 | 内容 |
|------|------|
| DB | `engine/data/deepcast.db`（SQLite WAL） |
| LLM | Ollama qwen2.5（ローカル） |
| TTS | Gemini TTS（Enceladus + Zephyr、男性2人対話、atempo=1.08） |
| 課金 | Gemini API従量課金済み（月上限3,000円） |
| ダッシュボード | http://localhost:8001 |

### 導入済み機能
- SPA（ページ遷移してもオーディオ再生が途切れない）
- 永続オーディオプレイヤー（Mini Player + プレイリスト + MediaSession API）
- iOS Safari オーディオ対応
- PWA（Service Worker + manifest.json）
- SEO最適化（JSON-LD構造化データ、OGP、BreadcrumbList）
- Google Analytics GA4
- RSSフィード（Apple Podcasts/Spotify/Amazon Music向け）
- 再生終了→記事ページ自動遷移（PVブースト）

### 未実装・未設定
- Stripe決済（アクションプランにあるが未着手）
- SNSアカウント（X, TikTok, YouTube等 — 未開設）
- メルマガ（未設定）
- AdSense（ads.txtはあるが広告表示は最小限）

---

## ファイル構成

```
G:\マイドライブ\0_deep cast\
├── index.html              トップページ（795行）
├── all-episodes.html       エピソード一覧
├── about.html              サービス説明
├── contact.html            お問い合わせ
├── privacy.html            プライバシーポリシー
├── terms.html              利用規約
├── tokushoho.html          特商法
├── copyright.html          著作権表記
│
├── episodes/
│   ├── episodes.json       ★ エピソード一覧データ（新しい順、idは連番）
│   ├── ep001.html〜        各エピソードの記事ページ（3000字以上のSEO記事）
│   ├── ep021.mp3〜         音声ファイル（番号体系が記事と異なるので注意）
│   └── （音声ファイル/  ← 日本語名バックアップ）
│
├── css/style.css           統合スタイルシート（823行）
├── js/
│   ├── spa-router.js       SPA + 永続オーディオプレイヤー（1351行、最重要JS）
│   └── main.js             最小限
│
├── assets/                 SVGアセット（icon, cover, og-image）
│
├── sw.js                   Service Worker（CACHE_NAME: "deepcast-v4"）
├── manifest.json           PWA設定
├── sitemap.xml             SEO用（lastmod更新を忘れずに）
├── feed.xml                RSSフィード（iTunes タグ完備）
├── ads.txt                 広告設定
├── robots.txt              検索エンジン制御
│
├── generate_episodes.py    ★ AI音声+台本自動生成（Gemini API）
├── test_tts.py             TTS単体テスト
├── test_dialogue.py        マルチスピーカーTTS実験
│
├── CLAUDE.md               ← このファイル
├── SEO対策プロンプト.md     新エピソード追加用コピペプロンプト
├── 100テーマリスト.md       ポッドキャスト企画100テーマ
└── 12時間単位アクションプラン.md  2ヶ月分のロードマップ
```

---

## 絶対に守るルール

### 1. リンクのhref
```
❌ href="index.html"      → ✅ href="./"
❌ href="../index.html"   → ✅ href="../"
```
**理由**: Cloudflare Pagesが `/index.html` を `/` に301リダイレクトする。SEOに悪影響。

### 2. サイトマップ
- `feed.xml` は `sitemap.xml` に入れない（RSSフィードはサイトマップ不要）

### 3. AdSense
- アドセンス広告のコードは既にあるページにのみ。新規追加しない。

### 4. デザイン方針
- AI典型的な purple/blue gradient は使わない
- Serif（Noto Serif JP）+ Sans（Noto Sans JP）の組み合わせ
- 人間的で温かい、編集的なビジュアル
- アクセントカラー: 緑 #3a8a44

---

## 新エピソード追加手順（全7ステップ）

「新エピソード追加して」と言われたら**全て実行**する。

### ステップ1: エピソード記事ページ作成（最重要）

既存の `episodes/ep001.html` をテンプレートにして新HTML作成。

**必須要素**:
- `<title>` 60-75字、「タイトル｜DeepCast AI」形式
- `<meta name="description">` 120-160字
- `<meta name="keywords">`
- `<link rel="canonical">` 正規URL
- OGPメタタグ一式（og:title, og:description, og:image, og:url, og:type="article"）
- Twitter Cardメタタグ一式
- JSON-LD構造化データ: **PodcastEpisode + BreadcrumbList を配列で**
- 本文: **3,000字以上**、h2を5-7個、h3適宜、highlight-box 2-4個、strongでキーワード強調
- 内部リンクは `href="../"` を使用（`href="../index.html"` 禁止）
- GA4トラッキングコード含める

**記事テンプレート**:
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

**BreadcrumbList フォーマット**:
```json
{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
  {"@type":"ListItem","position":1,"name":"DeepCast AI","item":"https://deepcast-ai.com/"},
  {"@type":"ListItem","position":2,"name":"エピソード一覧","item":"https://deepcast-ai.com/all-episodes.html"},
  {"@type":"ListItem","position":3,"name":"#番号 タイトル"}
]}
```

### ステップ2: episodes.json 更新
新エピソードを**配列の先頭**に追加。idは連番（現在の最大id + 1）。
```json
{
  "id": 4,
  "title": "タイトル",
  "description": "説明文",
  "date": "2026.MM.DD",
  "category": "society",
  "tags": ["タグ1", "タグ2"],
  "duration": "5:00",
  "audio": "episodes/epXXX.mp3",
  "article": "episodes/ep004.html"
}
```

### ステップ3: sitemap.xml 更新
新ページURLを追加。`lastmod` は当日日付。feed.xmlは入れない。

### ステップ4: feed.xml 更新
新エピソードの `<item>` を先頭に追加。既存フォーマットに合わせる。

### ステップ5: リダイレクトチェック
全HTMLで `href=".*index\.html` を検索。あれば `./` or `../` に修正。

### ステップ6: sw.js キャッシュ更新
`CACHE_NAME` のバージョン番号を +1。

### ステップ7: commit & push
```bash
git add -A && git commit -m "EP#X: タイトル（記事+音声+SEO）" && git push origin master
```

---

## SEO定期チェック

「SEOチェックして」と言われたら実行:

1. 全HTMLの `index.html` リンク残存チェック
2. `episodes.json` と `sitemap.xml` の整合性チェック
3. `episodes.json` と `feed.xml` の整合性チェック
4. 全ページの BreadcrumbList 構造化データ有無チェック
5. 全エピソードページの本文テキスト量チェック（3,000字以上か）
6. canonical URL の正確性チェック
7. OGPメタタグの欠落チェック

---

## 音声生成パイプライン（engine/main.py）

engine/ による自動生成フロー:

```
1. python main.py pipeline  → コンテンツ生成(Ollama qwen2.5) → 品質評価 → 公開
2. python main.py voice     → Gemini TTS対話生成(Enceladus+Zephyr) → ffmpeg加工(atempo=1.08)
3. python main.py publish   → HTML/JSON/RSS/sitemap更新
4. python main.py serve     → ダッシュボード(localhost:8001) + 全自動スケジューラ
```

**実行方法**:
```bash
cd "G:\マイドライブ\0_deep cast\engine"
python main.py pipeline   # エピソード生成〜公開まで一括
python main.py serve      # ダッシュボード起動
```

**課金**: Gemini API従量課金（月上限3,000円設定済み）。LLM部分はOllamaローカルなので無料。

---

## spa-router.js の重要な仕様

- `window.DeepCastAudio` がグローバルオーディオ管理オブジェクト
- ページ遷移は fetch() で HTML を取得し、nav/footer 間のコンテンツを差し替え
- オーディオ要素は DOM から外さず保持（遷移しても再生継続）
- 再生終了時に `articleToArticle` マップで記事ページへ自動遷移
- iOS Safari: touchstart/click で無音WAVを先読みして自動再生制限をバイパス

**触るときの注意**: オーディオ関連のDOMを安易に消すと再生が途切れる。

---

## デプロイフロー

```
コード変更 → git push origin master → Cloudflare Pages が自動ビルド → https://deepcast-ai.com/ に反映
```
特別なビルドコマンドなし。静的ファイルをそのまま配信。

---

## よくあるトラブルと対処

| 問題 | 原因 | 対処 |
|------|------|------|
| ページ遷移でオーディオが止まる | spa-router.jsのバグ or DOMからaudio要素が消えた | spa-router.jsのSPA遷移ロジックを確認 |
| iOS Safariで音が出ない | 自動再生制限 | spa-router.jsのiOS unlock処理を確認 |
| SEOで301リダイレクトが出る | `href="index.html"` を使っている | `href="./"` に修正 |
| キャッシュが更新されない | sw.jsのCACHE_NAME未更新 | バージョン番号を+1 |
| push後にサイトに反映されない | Cloudflare Pagesのビルド待ち | 数分待つ。GitHub側でcommit確認 |

---

## 企画リソース

- **100テーマリスト.md**: ポッドキャスト企画100テーマ（AI×社会、経済×心理、地政学×IT等）
- **12時間単位アクションプラン.md**: フェーズ1〜4のロードマップ（月¥0→¥300,000）
- **SEO対策プロンプト.md**: 新エピソード追加用のコピペプロンプト

---

## 日本語で対応すること
ユーザーとの会話は日本語で行う。
