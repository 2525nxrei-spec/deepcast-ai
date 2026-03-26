"""静的エピソード生成 — 外部API不要、ハードコードした記事本文からHTML+JSONを生成."""
import io
import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Windows cp932対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

SITE_DIR = Path("G:/マイドライブ/株式会社　礼/運用中/8_ディープキャスト")
EPISODES_DIR = SITE_DIR / "episodes"

EPISODES = [
    {
        "title": "AIが書いた論文を見抜けない — 学術界を揺るがす生成AIの衝撃",
        "tier": "pro",
        "body": """近年、生成AIの急速な進化が学術界に衝撃を与えている。GPT-4やClaude、Geminiといった大規模言語モデルが生成する文章は、もはや人間の専門家が書いたものと見分けがつかないレベルに達した。

## 検出ツールの限界

2024年に発表されたスタンフォード大学の研究によると、最新のAI検出ツールの精度はわずか60〜70%程度にとどまる。特に、AIが生成した文章を人間が軽く編集するだけで、検出率は30%以下にまで低下する。つまり、現時点でAI生成論文を確実に見抜く手段は存在しないのだ。

## 学術界への影響

問題は深刻だ。世界の主要学術誌への投稿論文のうち、推定10〜15%にAIが関与しているとされる。査読者自身がAIを使って査読するケースも報告されており、学術の信頼性の根幹が揺らいでいる。ネイチャー誌は2025年初頭にAI使用の全面開示を義務化したが、自己申告に頼る制度には限界がある。

## 新しいルール作りの必要性

重要なのは、AIの使用そのものを禁止することではない。AIをどう活用し、どこに人間の知的貢献を求めるかという新しいルール作りだ。研究の本質は「問いを立てる力」にある。AIが答えを書ける時代だからこそ、人間にしかできない創造的な問いかけの価値が、むしろ高まっているのではないだろうか。"""
    },
    {
        "title": "量子コンピュータが暗号を破る日 — いつ来るのか、どう備えるか",
        "tier": "pro",
        "body": """現在のインターネットセキュリティを支えるRSA暗号やECC暗号。これらは「大きな数の素因数分解は計算に膨大な時間がかかる」という前提に依存している。しかし、量子コンピュータはこの前提を根底から覆す可能性を持つ。

## 量子コンピュータの現在地

GoogleのWillow、IBMのCondor、日本の理化学研究所が開発する量子コンピュータは、いずれも1000量子ビットを超える段階に到達している。しかし、RSA-2048を現実的な時間で解読するには、約400万量子ビットの誤り耐性量子コンピュータが必要とされる。現時点では、その実現は2030年代後半から2040年代と予測されている。

## 「いま」から備える理由

では、まだ時間があるから安心かというと、そうではない。「Harvest Now, Decrypt Later（今収集し、後で復号する）」攻撃が現実の脅威として浮上している。国家レベルのアクターが暗号化された通信データを大量に保存し、量子コンピュータの実用化後に一気に復号するシナリオだ。

## ポスト量子暗号への移行

NISTは2024年にポスト量子暗号の標準規格を正式発表した。ML-KEM、ML-DSAといった格子暗号ベースのアルゴリズムが選定され、GoogleやAppleは既にブラウザやメッセージングアプリへの実装を開始している。量子時代の到来に備え、暗号のアップデートは「今すぐ」始めるべき課題なのだ。"""
    },
    {
        "title": "脳とAIの境界線 — ニューラリンクが開く人間拡張の未来",
        "tier": "pro",
        "body": """2024年、イーロン・マスク率いるニューラリンクが初の人体埋め込み試験を実施し、四肢麻痺の患者がBCI（脳コンピュータインターフェース）を通じてコンピュータを操作することに成功した。この出来事は、人間とテクノロジーの関係に根本的な問いを投げかけている。

## BCIの医療応用

現在のBCI技術は主に医療分野で進展している。ALS患者のコミュニケーション支援、脊髄損傷後のリハビリ、重度うつ病の治療など、従来は治療困難だった症状に対する画期的なアプローチとして期待されている。臨床試験では、脳に埋め込まれた電極が思考パターンを読み取り、ロボットアームを動かしたり、テキストを入力したりすることが可能になっている。

## 健常者への拡張という議論

問題が複雑になるのは、この技術が健常者の「能力拡張」に使われ始めた時だ。記憶力の強化、感覚の拡張、AIとの直接接続。これらが実現すれば、BCIを持つ人と持たない人の間に新たな格差が生まれる。

## 倫理的な課題

脳のデータは究極の個人情報だ。思考や感情が企業のサーバーに蓄積されることの意味を、私たちはまだ十分に理解していない。技術の進歩と倫理の議論を同時に進めること。それが、人間がテクノロジーに飲み込まれないための唯一の道筋ではないだろうか。"""
    },
    {
        "title": "SNSアルゴリズムが選挙を動かす — デジタル民主主義の光と影",
        "tier": "pro",
        "body": """2024年の各国選挙で、SNSプラットフォームのアルゴリズムが有権者の投票行動に大きな影響を与えたことが、複数の研究で明らかになっている。いいねやシェアの裏側で、民主主義の根幹が静かに変容しつつある。

## アルゴリズムが作る情報環境

TikTok、X（旧Twitter）、Instagram、YouTubeのレコメンドアルゴリズムは、ユーザーのエンゲージメントを最大化するよう設計されている。結果として、感情を強く刺激するコンテンツ、つまり怒りや恐怖を煽る政治的メッセージが優先的に表示される。MITの研究では、虚偽のニュースは真実のニュースよりも6倍速く拡散することが示されている。

## フィルターバブルの深刻化

個人の嗜好に最適化された情報フィードは、異なる意見に触れる機会を著しく減少させる。ハーバード大学の2025年の調査では、アメリカの有権者の68%が「自分と異なる政治的立場の意見をSNSでほとんど見ない」と回答している。

## プラットフォームの責任

EUのデジタルサービス法（DSA）はアルゴリズムの透明性を義務付けたが、実効性には疑問が残る。テクノロジー企業が利益を追求する以上、エンゲージメント最大化のインセンティブは変わらない。民主主義を守るために、私たち自身が情報の受け取り方を意識的に変えていく必要があるのかもしれない。"""
    },
    {
        "title": "なぜGAFAMは宇宙開発に巨額投資するのか — テック企業の宇宙戦略",
        "tier": "pro",
        "body": """Amazon創業者ジェフ・ベゾスのBlue Origin、SpaceX、Googleの衛星プロジェクト、Appleの衛星通信機能。巨大テック企業が次々と宇宙事業に参入している。その狙いは何か。

## 衛星インターネットという巨大市場

SpaceXのStarlinkは既に6000基以上の衛星を軌道上に展開し、世界70カ国以上でサービスを提供している。Amazon Project Kuiperも3200基の衛星打ち上げを計画中だ。世界人口の約40%、約30億人がまだインターネットにアクセスできていない。この「未接続人口」こそが、テック企業にとって最後の巨大市場なのだ。

## データセンターの限界と宇宙

地上のデータセンターは電力消費と冷却の問題に直面している。宇宙空間は自然冷却が可能で、太陽光発電のエネルギーも豊富だ。Microsoftは海底データセンターの実験を行い、将来的には宇宙空間でのコンピューティングも視野に入れている。

## 資源と覇権の争い

月や小惑星に含まれるレアアースやヘリウム3は、次世代テクノロジーの鍵を握る資源だ。宇宙条約の解釈を巡る国際的な議論が進む中、テック企業は既に先行投資を始めている。宇宙開発は、テクノロジー覇権の次のフロンティアとなりつつある。"""
    },
    {
        "title": "自動運転車の「トロッコ問題」 — AIに命の選択を任せられるか",
        "tier": "pro",
        "body": """自動運転技術が進化するにつれ、避けられない倫理的ジレンマが浮上している。事故が避けられない状況で、AIはどのような判断を下すべきなのか。

## レベル4自動運転の現実

2025年現在、WaymoやCruiseが特定都市でレベル4自動運転タクシーを運行している。テスラのFSD（Full Self-Driving）は依然としてレベル2だが、カメラのみで高度な判断を実現している。自動運転車による事故率は人間ドライバーの約半分というデータもあるが、事故が起きた時の責任の所在が大きな議論を呼んでいる。

## MITモラルマシン実験

MITが実施した「モラルマシン」実験では、233カ国1000万人以上の回答を分析した。結果、文化や国によって倫理的判断が大きく異なることが判明した。例えば、若者と高齢者のどちらを優先するかという問いに対し、東アジアでは高齢者を尊重する傾向が強く、欧米では若者を優先する傾向が見られた。

## 統一基準は可能か

自動運転車のアルゴリズムにどのような倫理基準を組み込むべきか。この問いに普遍的な正解はない。重要なのは、その判断プロセスを透明化し、社会全体で議論を続けることだ。AIに命の選択を任せるということは、私たち人間がその判断基準を事前に決めるという、極めて重い責任を引き受けることを意味している。"""
    },
    {
        "title": "ディープフェイクが変える情報戦 — 真実を見極める時代の終わり",
        "tier": "pro",
        "body": """AIが生成するディープフェイク技術は、もはや専門家でも見分けが困難なレベルに達した。この技術が社会に与える影響は、私たちの想像をはるかに超えている。

## 進化するディープフェイク技術

2025年のディープフェイク技術は、数秒の音声サンプルから本人そっくりの音声を合成し、1枚の写真からリアルタイムの動画を生成できる段階にある。生成にかかる時間はわずか数分。コストはほぼゼロだ。かつては国家機関レベルの技術だったものが、スマートフォンアプリで誰でも利用可能になっている。

## 情報戦への応用

ウクライナ紛争では、ゼレンスキー大統領の降伏を宣言する偽動画が拡散した。企業のCEOの偽音声で株価を操作する詐欺事件も増加している。FBIの報告では、ディープフェイクを使った詐欺被害は2024年だけで250億ドルに達したと推定されている。

## 真正性の証明が鍵

問題への対策として、コンテンツの出所を証明する「C2PA」規格が注目されている。Adobe、Microsoft、BBC、ソニーなどが参加するこのイニシアチブは、写真や動画の撮影時にデジタル署名を埋め込み、改変を検出可能にする。「偽物を見破る」のではなく「本物を証明する」という逆転の発想が、情報の信頼性を守る鍵になるかもしれない。"""
    },
    {
        "title": "電子ゴミが地球を覆う — テクノロジーの裏にある環境コスト",
        "tier": "free",
        "body": """毎年買い替えるスマートフォン、数年で陳腐化するパソコン、次々に発売される新型ガジェット。私たちのテクノロジー消費の裏側には、深刻な環境問題が横たわっている。

## 年間6200万トンの電子ゴミ

国連の報告によると、2024年に世界で発生した電子廃棄物は6200万トン。これはエッフェル塔6万8000基分の重さに相当する。しかし、適切にリサイクルされているのはわずか22%に過ぎない。残りの78%は埋め立て処分されるか、途上国に輸出されて不適切な方法で処理されている。

## 見えない環境コスト

1台のスマートフォンの製造には、約70種類の元素が使われ、製造過程で約70kgのCO2が排出される。バッテリーに使われるリチウムやコバルトの採掘は、水資源の枯渇や児童労働の問題と直結している。また、データセンターの電力消費は世界全体の電力の約2%を占め、航空産業と同等のCO2を排出している。

## サーキュラーエコノミーへの転換

解決策として注目されるのが、製品の修理する権利（Right to Repair）の法制化だ。EUは2025年からスマートフォンのバッテリー交換を義務化し、修理マニュアルの公開を求めている。テクノロジーの恩恵を享受しながら、地球環境を守る。この両立こそが、次世代のイノベーションに求められる最大の課題だ。"""
    },
    {
        "title": "AIが医師を超える日 — 診断精度99%の衝撃と残る課題",
        "tier": "free",
        "body": """AIの医療分野への応用が急速に進んでいる。画像診断における精度は既に人間の専門医を上回るケースも出ているが、AIが医師を「超える」とはどういう意味なのだろうか。

## 画像診断の革命

Google Healthが開発した乳がん検出AIは、マンモグラフィー画像の診断において、放射線科医の平均精度を11.5%上回った。皮膚がんの画像診断では、AIの精度は95%を超え、ベテラン皮膚科医の87%を大きく上回っている。網膜画像から糖尿病性網膜症を検出するAIは、インドやタイの農村部で既に実用化されている。

## AIの限界

しかし、AIには決定的な弱点がある。学習データに偏りがあれば、特定の人種や年齢層で精度が大きく低下する。また、AIは「なぜそう判断したか」を説明できない場合が多く、医療の現場で最も重要な「患者への説明」ができない。さらに、複数の疾患が同時に存在する複合的な症例では、依然として人間の総合的判断力が必要とされる。

## 共存の未来

理想的な形は、AIが一次スクリーニングを担い、人間の医師が最終判断と治療方針の決定を行うハイブリッドモデルだ。AIは医師を代替するのではなく、医師の能力を拡張するツールとして位置づけるべきだろう。テクノロジーと人間の知恵の融合。それが、医療の未来を切り拓く鍵となる。"""
    },
    {
        "title": "プログラミング不要の時代 — ノーコード革命は本物か幻か",
        "tier": "free",
        "body": """「プログラミングを学ばなくてもアプリが作れる」。ノーコード・ローコードプラットフォームは、この約束を掲げて急成長を遂げている。果たしてこの革命は本物なのだろうか。

## 市場の爆発的成長

ノーコード市場は2025年時点で約320億ドル規模に達し、年間成長率は25%を超えている。Bubble、Adalo、FlutterFlowといったプラットフォームでは、ドラッグ&ドロップの操作だけでWebアプリやモバイルアプリを構築できる。NotionやAirtableのようなツールも、データベースアプリケーションの構築をプログラミング不要で実現している。

## 実際の導入事例

スタートアップの約35%がMVP（最小実行可能製品）の構築にノーコードツールを使用しているというデータがある。大企業でも、社内の業務自動化にMicrosoft Power PlatformやGoogle AppSheetが広く採用されている。ある調査では、ノーコードで構築されたアプリの開発速度は、従来のコーディングと比較して10倍速いという結果が出ている。

## 限界と共存

ただし、高度なカスタマイズ、大規模データ処理、リアルタイム通信など、ノーコードでは対応困難な領域は確実に存在する。また、プラットフォームへの依存度が高く、ベンダーロックインのリスクも無視できない。現実的には、ノーコードが「プログラマー不要」の時代を作るのではなく、「誰もがクリエイターになれる」時代の入り口を開いたと見るべきだろう。プログラミングの知識は、依然として深い価値を持ち続ける。"""
    },
]

def create_episode_html(ep_num, title, body, description):
    """エピソードHTMLを生成"""
    ep_str = f"ep{ep_num:03d}"
    today = datetime.now().strftime("%Y-%m-%d")

    # 本文をHTML化
    sections = body.strip().split("\n\n")
    article_html = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith("## "):
            heading = section.replace("## ", "").strip()
            article_html += f'        <h2>{heading}</h2>\n'
        else:
            article_html += f'        <p>{section}</p>\n'

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>#{ep_num} {title}｜DeepCast AI</title>
<meta name="description" content="{description[:160]}">
<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html">
<meta property="og:title" content="#{ep_num} {title}｜DeepCast AI">
<meta property="og:description" content="{description[:160]}">
<meta property="og:url" content="https://deepcast-ai.com/episodes/{ep_str}.html">
<meta name="twitter:title" content="#{ep_num} {title}｜DeepCast AI">
<meta name="twitter:description" content="{description[:160]}">
<link rel="stylesheet" href="/assets/css/style.css">
<link rel="stylesheet" href="/css/style.css">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"DeepCast AI","item":"https://deepcast-ai.com/"}},{{"@type":"ListItem","position":2,"name":"#{ep_num} {title}","item":"https://deepcast-ai.com/episodes/{ep_str}.html"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"PodcastEpisode","episodeNumber":{ep_num},"datePublished":"{today}","name":"#{ep_num} {title}","url":"https://deepcast-ai.com/episodes/{ep_str}.html"}}
</script>
</head>
<body>
<header class="site-header">
  <nav class="nav">
    <a href="/" class="nav__logo">DeepCast AI</a>
    <div class="nav__links">
      <a href="/all-episodes.html" class="nav__link">全エピソード</a>
      <a href="/pages/pricing.html" class="nav__link">料金</a>
    </div>
  </nav>
</header>
<main class="episode-page">
  <article class="episode-detail">
    <div class="episode-detail__header">
      <span class="episode-detail__number">#{ep_num}</span>
      <h1 class="episode-detail__title">{title}</h1>
      <time class="episode-detail__date">{today}</time>
    </div>
    <div class="episode-detail__player">
      <p style="color:#8e8e93;font-size:0.9rem;padding:1rem;background:#f5f5f7;border-radius:8px;text-align:center;">
        音声は準備中です。テキストでお楽しみください。
      </p>
    </div>
    <div class="article-body">
{article_html}
    </div>
  </article>
</main>
<footer class="site-footer">
  <p>&copy; 2026 DeepCast AI — 濱田礼</p>
  <nav>
    <a href="/pages/terms.html">利用規約</a>
    <a href="/pages/privacy.html">プライバシーポリシー</a>
    <a href="/pages/tokushoho.html">特商法</a>
    <a href="/pages/contact.html">お問い合わせ</a>
  </nav>
</footer>
<script src="/assets/js/auth.js?v=20260327"></script>
</body>
</html>'''

    out_path = EPISODES_DIR / f"{ep_str}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  -> {out_path.name}")
    return out_path


def main():
    # episodesディレクトリ確認
    EPISODES_DIR.mkdir(exist_ok=True)

    # 既存ファイル削除
    print("既存エピソードファイルを削除...")
    for i in range(1, 20):
        ep_str = f"ep{i:03d}"
        for ext in [".html", ".mp3"]:
            fp = EPISODES_DIR / f"{ep_str}{ext}"
            if fp.exists():
                fp.unlink()
                print(f"  削除: {fp.name}")

    episodes_json = []
    total = len(EPISODES)
    today = datetime.now().strftime("%Y.%m.%d")

    print(f"\n生成開始: {total}本\n")

    for i, ep in enumerate(EPISODES):
        ep_num = i + 1
        ep_str = f"ep{ep_num:03d}"
        title = ep["title"]
        body = ep["body"]
        tier = ep["tier"]

        print(f"[{ep_str}] {title} [{tier.upper()}]")

        # 説明文
        description = body[:200].replace("\n", " ").strip()
        if len(description) > 150:
            description = description[:150] + "..."

        # HTML生成
        create_episode_html(ep_num, title, body, description)

        # タグ生成
        tags = [w.strip() for w in title.replace("—", " ").replace("―", " ").split() if len(w.strip()) > 1][:4]

        # JSON追加
        episodes_json.append({
            "id": ep_num,
            "title": title,
            "description": description,
            "date": today,
            "category": "tech",
            "tags": tags,
            "duration": "2:30",
            "audio": "",
            "article": f"episodes/{ep_str}.html",
            "language": "ja",
            "tier": tier,
        })

    # episodes.json保存（新しい順にソート）
    episodes_json.reverse()
    json_path = EPISODES_DIR / "episodes.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(episodes_json, f, ensure_ascii=False, indent=2)

    print(f"\n完了: {total}本生成")
    print(f"episodes.json: {len(episodes_json)}件")
    print(f"Free: {sum(1 for e in episodes_json if e['tier'] == 'free')}本")
    print(f"Pro: {sum(1 for e in episodes_json if e['tier'] == 'pro')}本")


if __name__ == "__main__":
    main()
