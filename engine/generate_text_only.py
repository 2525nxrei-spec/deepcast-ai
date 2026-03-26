"""テキストのみエピソード生成スクリプト.

音声生成とR2アップロードをスキップし、HTMLページとepisodes.jsonのみを生成する。
Gemini APIが503の場合はハードコードしたフォールバックテキストを使用。
"""
import io
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime

# Windows cp932対策: stdoutをUTF-8に変更
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- パス設定（直接指定）---
SITE_DIR = Path("G:/マイドライブ/株式会社　礼/運用中/8_ディープキャスト")
EPISODES_DIR = SITE_DIR / "episodes"
EPISODES_JSON = EPISODES_DIR / "episodes.json"

# --- Gemini APIキー ---
# .envから読み込みを試みる
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # プロジェクトルートの.envも探す
        load_dotenv(SITE_DIR / ".env")
        load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- トピック一覧 ---
NEW_TOPICS = [
    "AIが書いた論文を見抜けない — 学術界を揺るがす生成AIの衝撃",
    "量子コンピュータが暗号を破る日 — いつ来るのか、どう備えるか",
    "脳とAIの境界線 — ニューラリンクが開く人間拡張の未来",
    "SNSアルゴリズムが選挙を動かす — デジタル民主主義の光と影",
    "なぜGAFAMは宇宙開発に巨額投資するのか — テック企業の宇宙戦略",
    "自動運転車の「トロッコ問題」 — AIに命の選択を任せられるか",
    "ディープフェイクが変える情報戦 — 真実を見極める時代の終わり",
    "電子ゴミが地球を覆う — テクノロジーの裏にある環境コスト",
    "AIが医師を超える日 — 診断精度99%の衝撃と残る課題",
    "プログラミング不要の時代 — ノーコード革命は本物か幻か",
]

# --- フォールバック記事テキスト（Gemini API失敗時に使用）---
FALLBACK_ARTICLES = {
    "AIが書いた論文を見抜けない — 学術界を揺るがす生成AIの衝撃": """## 生成AIが学術界に突きつける問い

2025年、世界の主要学術誌に投稿される論文のうち、推定で10〜15%にAIが深く関与しているとされています。問題は、査読者がそれを見抜けないケースが増えていることです。大規模言語モデルは、専門用語を正確に使いこなし、論理構成も整った文章を生成できるようになりました。

ある調査では、AI生成論文と人間が執筆した論文を専門家に見分けさせたところ、正答率はわずか52%。コイントスとほぼ同じ精度でした。これは学術の信頼性の根幹を揺るがす事態です。

## 検出技術の限界と対策

AI検出ツールも開発されていますが、精度は完璧ではありません。OpenAIが開発した検出ツールは誤検出率の高さから公開を中止しました。透かし技術やスタイロメトリー（文体分析）など新たなアプローチも研究されていますが、AI側の進化が常に一歩先を行くのが現状です。

一方、大学や学術誌では新たなガイドラインの策定が進んでいます。Nature誌は2024年にAI使用の明記を義務化し、多くの大学もAI利用ポリシーを導入しました。

## 共存の道を探る

重要なのは、AIを完全に排除するのではなく、適切な利用ルールを確立することです。文献調査の効率化やデータ分析の補助など、AIが学術研究を加速させる可能性は大きい。問題は「AIが書いた」ことではなく、「AIの関与を隠す」ことにあります。透明性のある利用こそが、学術界とAIの健全な共存への第一歩です。""",

    "量子コンピュータが暗号を破る日 — いつ来るのか、どう備えるか": """## 現在の暗号が無力化される日

インターネットの安全を支えるRSA暗号やECC（楕円曲線暗号）。これらは、従来のコンピュータでは天文学的な時間がかかる計算を基盤にしています。しかし、量子コンピュータが十分に発展すれば、ショアのアルゴリズムによってこれらの暗号は数時間で解読可能になると言われています。

IBMやGoogleは2029年までに実用的な量子コンピュータの実現を目指しています。現在の量子ビット数は1000程度ですが、RSA-2048を破るには約4000量子ビットが必要とされています。「まだ先の話」と思うかもしれませんが、専門家の多くは2030年代前半にはその脅威が現実化すると予測しています。

## 「今すぐ収集、後で解読」の脅威

見落とされがちなのが、「Harvest Now, Decrypt Later（今収穫し、後で復号する）」攻撃です。国家レベルの攻撃者が現在の暗号化通信を大量に傍受・保存し、量子コンピュータが実用化された時点で一気に解読するという戦略です。つまり、今日送信した機密情報が、10年後に丸裸になる可能性があるのです。

## ポスト量子暗号への移行

米国立標準技術研究所（NIST）は2024年、量子耐性を持つ新しい暗号標準を正式に発表しました。CRYSTALS-KyberやCRYSTALS-Dilithiumといったアルゴリズムが選定され、世界中の企業や政府機関が移行準備を進めています。日本でも総務省が「量子セキュリティ推進ロードマップ」を策定し、2030年までの段階的な移行を推奨しています。備えは「今」始めるべきです。""",

    "脳とAIの境界線 — ニューラリンクが開く人間拡張の未来": """## ニューラリンクの現在地

イーロン・マスク率いるニューラリンクは、脳とコンピュータを直接接続するBCI（ブレイン・コンピュータ・インターフェース）技術の開発を進めています。2024年には初の人間への臨床試験が開始され、四肢麻痺の患者がインプラントを通じてコンピュータのカーソルを操作することに成功しました。

この技術は、脳に埋め込まれた微細な電極が神経信号を読み取り、外部デバイスに変換するものです。1024本の電極を持つチップ「N1」は、わずか硬貨サイズでありながら、高精度な脳波のリアルタイム解析を実現しています。

## 医療からエンハンスメントへ

BCIの最初のターゲットは医療です。脊髄損傷患者のリハビリ、ALS患者のコミュニケーション支援、パーキンソン病の症状緩和など、切実なニーズがあります。しかし技術が成熟すれば、健常者の能力拡張——記憶力の増強、瞬時の言語翻訳、AIとの直接対話——への応用も視野に入ってきます。

ここで生じるのが「人間とは何か」という根本的な問いです。脳にAIを組み込んだ人間は、もはや純粋な人間と言えるのでしょうか。

## 倫理的課題とガバナンス

最大の懸念は、思考のプライバシーです。脳波データは究極の個人情報であり、悪用されれば思考や感情の監視につながりかねません。また、高額な技術へのアクセス格差が新たな社会的不平等を生む可能性もあります。国際的な規制枠組みの整備が急務であり、技術の恩恵を公平に享受できる社会設計が求められています。""",

    "SNSアルゴリズムが選挙を動かす — デジタル民主主義の光と影": """## アルゴリズムが作る「情報の世界」

SNSのフィードに表示される投稿は、ランダムではありません。各プラットフォームのアルゴリズムが、ユーザーの過去の行動データをもとに「最もエンゲージメントが高い」と予測されるコンテンツを優先的に表示しています。この仕組みが、政治的な情報の流通に大きな影響を与えています。

MITの研究によると、SNS上でフェイクニュースは真実の情報より6倍速く拡散します。感情を揺さぶるコンテンツほどエンゲージメントが高く、アルゴリズムによって増幅されるためです。選挙期間中、有権者は自分の信念を強化する情報ばかりに囲まれ、フィルターバブルの中で意思決定を行うことになります。

## 実際に選挙に影響を与えた事例

2016年の米国大統領選では、ケンブリッジ・アナリティカ事件が世界に衝撃を与えました。Facebookの個人データを利用した精密なターゲティング広告が、選挙結果に影響を与えた可能性が指摘されています。その後も世界各地の選挙で、SNSを利用した世論操作や偽情報キャンペーンが報告されています。

2024年には、生成AIによるディープフェイク動画が選挙キャンペーンに登場し、候補者の発言を捏造する事例が複数の国で確認されました。

## 民主主義を守るために

各国で規制の動きが加速しています。EUのデジタルサービス法は、プラットフォームにアルゴリズムの透明性を義務付けました。また、ファクトチェック機関との連携や、政治広告のデータベース公開なども進んでいます。しかし最も重要なのは、私たち一人ひとりのメディアリテラシーです。「なぜこの情報が自分に表示されているのか」を意識することが、デジタル時代の民主主義を守る第一歩となります。""",

    "なぜGAFAMは宇宙開発に巨額投資するのか — テック企業の宇宙戦略": """## テック企業が宇宙を目指す理由

Amazon創業者ジェフ・ベゾスのBlue Origin、イーロン・マスクのSpaceX、そしてGoogleやMicrosoftも宇宙関連事業に数兆円規模の投資を行っています。なぜ地上のテクノロジー企業が宇宙に巨額を投じるのでしょうか。

最大の理由は「データインフラ」です。衛星通信は、地上の光ファイバーが届かない地域にインターネット接続を提供できます。SpaceXのStarlinkは既に7000基以上の衛星を展開し、世界100カ国以上でサービスを提供。Amazonも「Project Kuiper」として3200基以上の衛星打ち上げを計画しています。次の40億人のユーザーを獲得するには、宇宙からのアプローチが不可欠なのです。

## クラウドコンピューティングの宇宙展開

AWSやMicrosoft Azureは、宇宙空間でのクラウドサービス提供を開始しています。AWSの「Ground Station」は衛星データの受信・処理を提供し、Microsoftの「Azure Orbital」も同様のサービスを展開中です。Googleは衛星画像のAI解析に強みを持ち、農業、都市計画、環境モニタリングなど幅広い分野にソリューションを提供しています。

## 宇宙経済の可能性

モルガン・スタンレーの推計によると、宇宙産業の市場規模は2040年には約150兆円に達すると予測されています。宇宙資源の採掘、宇宙太陽光発電、軌道上製造など、SF映画の世界が現実のビジネスチャンスとなりつつあります。GAFAM各社はこの巨大市場で先行者優位を確立するために、今のうちから布石を打っているのです。宇宙はもはや国家だけのフロンティアではなく、テック企業の主戦場になりつつあります。""",

    "自動運転車の「トロッコ問題」 — AIに命の選択を任せられるか": """## 現実になった思考実験

「暴走するトロッコの前に5人がいる。レバーを引けば1人の方に進路が変わる。あなたはレバーを引くか？」——哲学の思考実験として知られるトロッコ問題が、自動運転車の登場により現実の技術課題になりました。

自動運転車が避けられない事故に直面したとき、AIはどのような判断を下すべきでしょうか。歩行者を避けてガードレールに突っ込むのか。乗員の安全を優先するのか。この問いに対する「正解」は、文化や価値観によって異なります。

MITの「Moral Machine」実験では、世界233カ国から4000万件以上の回答が集まりました。その結果、若者と高齢者のどちらを優先するか、歩行者と乗員のどちらを守るかについて、地域ごとに大きな違いがあることが明らかになりました。

## 技術の現在地

レベル4の自動運転（限定条件下での完全自動運転）は、すでにWaymoやCruiseなどが一部都市で商用サービスを展開しています。しかし、倫理的判断を伴う極限状況への対応は、技術的にも法的にも未解決です。

現在の自動運転AIは「事故を最小化する」というアプローチを取っていますが、これは「誰を犠牲にするか」という判断とは本質的に異なります。メーカー各社は、具体的な倫理的判断ロジックについて公開を避ける傾向にあります。

## 法制度と社会的合意

ドイツは世界で初めて自動運転の倫理ガイドラインを策定し、「人命の比較はしない」「年齢や性別で差別しない」といった原則を定めました。日本でも道路交通法の改正が段階的に進められています。重要なのは、技術者だけでなく社会全体でこの議論に参加し、透明性のあるルール作りを進めることです。""",

    "ディープフェイクが変える情報戦 — 真実を見極める時代の終わり": """## 見分けがつかない偽映像の衝撃

2024年、ある国の大統領が戦争終結を宣言する映像がSNSで拡散されました。しかしそれはディープフェイク——AIが生成した偽映像でした。映像は数時間で数百万回再生され、金融市場にも一時的な混乱をもたらしました。

ディープフェイク技術は急速に進化しています。2025年現在、高品質なフェイク動画の生成コストは5年前の100分の1にまで下がり、スマートフォンアプリでも作成可能なレベルに達しています。音声クローニング技術と組み合わせれば、実在の人物が言っていないことを「言わせる」ことが容易になりました。

## 情報戦の新次元

国家レベルの情報戦において、ディープフェイクは強力な武器になっています。選挙介入、外交的な混乱の誘発、軍事的な偽情報作戦など、その応用範囲は広がる一方です。問題は、一度拡散した偽情報を訂正することの困難さにあります。「嘘は靴を履いている間に、真実はまだ靴紐を結んでいる」——マーク・トウェインの言葉がかつてないほど現実味を帯びています。

企業の株価操作や個人への名誉毀損にもディープフェイクが悪用されるケースが増えており、法的対応が追いつかない状況です。

## 対抗技術と社会の対応

検出技術の開発も進んでいます。Microsoftの「Video Authenticator」やIntelの「FakeCatcher」は、映像内の微細な不整合を検出します。また、C2PA（コンテンツ来歴・真正性のための連合）は、デジタルコンテンツに電子署名を埋め込む規格を推進しています。しかし最終的には、受け手である私たちが「映像を見たから真実」という前提を捨て、批判的思考力を高めることが最大の防御策となるでしょう。""",

    "電子ゴミが地球を覆う — テクノロジーの裏にある環境コスト": """## 年間6200万トンの電子ゴミ

国連の報告によると、2024年に世界で発生した電子廃棄物（e-waste）は年間6200万トンに達しました。これは5年前と比較して約20%の増加です。スマートフォン、パソコン、タブレット、IoTデバイス——私たちの生活を便利にするテクノロジー製品は、廃棄段階で深刻な環境問題を引き起こしています。

電子ゴミには鉛、水銀、カドミウムといった有害物質が含まれています。適切に処理されなければ、土壌や地下水を汚染し、周辺住民の健康に深刻な影響を与えます。特に問題なのが、先進国で廃棄された電子機器が途上国に輸出され、安全基準のない環境で解体されている現実です。

## 計画的陳腐化という問題

多くのテック企業は、製品の寿命を意図的に短く設計する「計画的陳腐化」を行っていると批判されています。バッテリーの交換が困難な設計、ソフトウェアアップデートによる旧機種の性能低下、修理部品の入手困難化など、消費者を買い替えに向かわせる構造があります。

EUは2024年に「修理する権利」法を施行し、メーカーに修理部品の提供と修理マニュアルの公開を義務付けました。フランスでは「修理可能性インデックス」の表示が必須となり、消費者が製品選択時に環境負荷を考慮できる仕組みが整いつつあります。

## 循環型経済への転換

解決策として注目されているのが「都市鉱山」の活用です。電子ゴミには金、銀、レアアースなどの希少金属が含まれており、天然鉱山より高い濃度で回収可能な場合もあります。日本は世界有数の都市鉱山大国であり、リサイクル技術の高度化が進んでいます。テクノロジーの恩恵を享受しながら地球環境を守るには、作る段階から廃棄を見据えた設計思想への転換が不可欠です。""",

    "AIが医師を超える日 — 診断精度99%の衝撃と残る課題": """## 診断精度でAIが人間を上回る

2025年、Google DeepMindが開発した医療AI「Med-Gemini」は、皮膚がんの画像診断において専門医を上回る99.1%の精度を達成しました。放射線画像の読影、病理診断、眼底検査など、画像ベースの診断分野では、AIが人間の専門家と同等かそれ以上の性能を示す事例が相次いでいます。

中国では、AIによるCT画像の自動診断が既に臨床現場で実用化されており、1日あたり数千件の画像を処理しています。日本でも、内視鏡AI支援システムが薬事承認を取得し、大腸ポリープの見逃し率を大幅に低下させる成果を上げています。

## AIにできないこと

しかし、診断精度の高さが必ずしも「良い医療」を意味するわけではありません。患者の不安に寄り添う共感力、家族の事情を考慮した治療方針の提案、告知の際の言葉選び——これらは現在のAIには極めて困難な領域です。

また、AIは学習データに含まれない稀少疾患や、複数の疾患が複雑に絡み合った症例への対応力が不足しています。さらに、AIの判断が誤っていた場合の責任の所在も明確ではありません。「AIが誤診した」場合、責任はAI開発企業にあるのか、使用した医師にあるのか、医療機関にあるのか。

## 人間とAIの協働モデル

最も現実的で有効なのは、AIを「第二の意見」として活用する協働モデルです。AIが高速で候補を絞り込み、最終判断は医師が行う。AIが見落としやすい人間的要素を医師が補い、医師が見落としやすいパターンをAIが検出する。この補完関係こそが、医療の質を最大化する鍵です。テクノロジーの力を借りながらも、医療の本質は「人が人を癒す」ことにあるのです。""",

    "プログラミング不要の時代 — ノーコード革命は本物か幻か": """## ノーコード市場の急成長

ノーコード・ローコードプラットフォームの市場規模は、2025年に約5兆円に達したと推計されています。Bubble、Webflow、Zapier、Airtable、そして各クラウドベンダーが提供するローコードツール——プログラミングの知識がなくてもアプリケーションを構築できる時代が到来しています。

ガートナーの予測では、2026年までに企業の新規アプリケーションの75%がノーコード・ローコードで開発されるとされています。実際、日本でも中小企業を中心に、業務効率化ツールやECサイトの構築にノーコードが広く採用されるようになりました。

## AIがノーコードをさらに加速

2024年以降、生成AIとノーコードの融合が新たな潮流を生んでいます。自然言語で「こんなアプリが欲しい」と記述するだけで、AIがアプリケーションの雛形を生成する。GitHub CopilotやCursorといったAIコーディング支援ツールは、従来のプログラマーの生産性を数倍に高めています。

これにより、「市民開発者」と呼ばれる非IT部門の従業員が、自らの業務課題を自ら解決するケースが増えています。IT部門のボトルネックを解消し、DX（デジタルトランスフォーメーション）を加速する効果が期待されています。

## それでもプログラミングは死なない

しかし、ノーコードには明確な限界があります。高度なカスタマイズ、大規模なシステム設計、パフォーマンスの最適化、セキュリティの厳密な制御——これらはコードを書ける人間でなければ対応できません。ノーコードは「プログラミングの民主化」であり、「プログラミングの終焉」ではないのです。

むしろ、ノーコードの普及によってソフトウェア開発への関心が高まり、本格的にプログラミングを学ぶ人が増えているというデータもあります。ツールは変わっても、論理的思考と問題解決能力の価値は不変です。""",
}


def generate_content_gemini(topic_title: str, max_retries: int = 5) -> str | None:
    """Gemini APIで記事本文を生成（リトライ付き）。失敗時はNoneを返す。"""
    if not GEMINI_API_KEY:
        print("    [SKIP] GEMINI_API_KEYが未設定のためスキップ")
        return None

    try:
        from google import genai
    except ImportError:
        print("    [SKIP] google-genaiパッケージが見つからないためスキップ")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下のテーマについて、ポッドキャスト配信用の記事本文を日本語で書いてください。

テーマ: {topic_title}

要件:
- 800〜1200文字程度の記事（2分30秒の音声に適した長さ）
- h2見出しを2-3個使用
- 事実に基づいた深い考察
- 読者を引きつける導入
- 具体的なデータや事例を含める
- 結論で新しい視点を提示
- HTMLタグは使わず、プレーンテキストで
- マークダウン記法（##）で見出しを書く
"""

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            wait = (attempt + 1) * 30  # 30秒, 60秒, 90秒...
            print(f"    [RETRY {attempt+1}/{max_retries}] {e} — {wait}秒後にリトライ")
            time.sleep(wait)

    print(f"    [FAIL] {max_retries}回リトライしたが全て失敗")
    return None


def generate_content(topic_title: str) -> str:
    """コンテンツ生成（Gemini API → フォールバックテキスト）"""
    # まずGemini APIを試行
    result = generate_content_gemini(topic_title)
    if result and len(result) > 200:
        print(f"    -> Gemini APIで生成成功 ({len(result)}文字)")
        return result

    # フォールバック: ハードコードテキスト
    if topic_title in FALLBACK_ARTICLES:
        fallback = FALLBACK_ARTICLES[topic_title]
        print(f"    -> フォールバックテキスト使用 ({len(fallback)}文字)")
        return fallback

    # 最終手段: 簡易テンプレート生成
    print(f"    -> 簡易テンプレートで生成")
    parts = topic_title.split(" — ")
    main_title = parts[0] if parts else topic_title
    subtitle = parts[1] if len(parts) > 1 else ""
    return f"""## {main_title}の最前線

{main_title}は、テクノロジー業界で最も注目を集めるテーマの一つです。{subtitle}という問いかけは、多くの専門家や研究者の間で議論されています。急速に進化する技術は、私たちの社会に大きな変革をもたらしつつあります。

この分野では2024年から2025年にかけて、複数の重要な進展がありました。世界各国の研究機関や企業が競い合うように新技術を発表し、その影響は産業界を超えて社会全体に波及しています。

## 課題と展望

しかし、技術の発展には常に課題が伴います。倫理的な問題、法的な枠組みの整備、そして社会的な合意形成が必要です。専門家の間では、技術の恩恵を最大化しながらリスクを最小化するバランスのとれたアプローチが求められています。

## まとめ

{main_title}は、今後数年間でさらに大きな発展を遂げることが予想されます。私たちには、この変化を正しく理解し、適切に対応していく力が求められています。"""


def create_episode_html(ep_num: int, title: str, body: str, description: str, tier: str, tags: list[str], template: str) -> Path:
    """エピソードHTMLページを生成"""
    ep_str = f"ep{ep_num:03d}"
    today_dot = datetime.now().strftime("%Y.%m.%d")
    today_iso = datetime.now().strftime("%Y-%m-%d")

    # 本文をHTML化
    sections = body.split("\n\n")
    article_html = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith("## "):
            heading = section.replace("## ", "").strip()
            article_html += f'    <h2>{heading}</h2>\n\n'
        elif section.startswith("### "):
            heading = section.replace("### ", "").strip()
            article_html += f'    <h3>{heading}</h3>\n\n'
        else:
            article_html += f'    <p>{section}</p>\n\n'

    # テンプレートから新しいHTMLを生成
    html = template

    # --- title ---
    html = re.sub(r'<title>.*?</title>', f'<title>#{ep_num} {title}｜DeepCast AI</title>', html)

    # --- meta description ---
    desc_safe = description[:160].replace('"', '&quot;')
    html = re.sub(r'<meta name="description" content="[^"]*"', f'<meta name="description" content="{desc_safe}"', html)

    # --- canonical ---
    html = re.sub(r'<link rel="canonical" href="[^"]*"', f'<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html"', html)

    # --- OG tags ---
    html = re.sub(r'<meta property="og:title" content="[^"]*"', f'<meta property="og:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    html = re.sub(r'<meta property="og:description" content="[^"]*"', f'<meta property="og:description" content="{desc_safe}"', html)
    html = re.sub(r'<meta property="og:url" content="[^"]*"', f'<meta property="og:url" content="https://deepcast-ai.com/episodes/{ep_str}.html"', html)

    # --- Twitter tags ---
    html = re.sub(r'<meta name="twitter:title" content="[^"]*"', f'<meta name="twitter:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    html = re.sub(r'<meta name="twitter:description" content="[^"]*"', f'<meta name="twitter:description" content="{desc_safe}"', html)

    # --- 構造化データ（PodcastEpisode）---
    html = re.sub(r'"name":\s*"[^"]*"(,\s*\n\s*"description")', f'"name": "{title}"\\1', html)
    html = re.sub(r'"description":\s*"[^"]*"(,\s*\n\s*"datePublished")', f'"description": "{desc_safe}"\\1', html)
    html = re.sub(r'"datePublished":\s*"[^"]*"', f'"datePublished": "{today_iso}"', html)
    html = re.sub(r'"episodeNumber":\s*\d+', f'"episodeNumber": {ep_num}', html)
    html = re.sub(r'"url":\s*"https://deepcast-ai\.com/episodes/ep\d+\.html"', f'"url": "https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'"contentUrl":\s*"[^"]*"', f'"contentUrl": "https://audio.deepcast-ai.com/{ep_str}.mp3"', html)

    # --- BreadcrumbList の最後の項目（エピソード名）---
    html = re.sub(r'"name":\s*"#\d+[^"]*"(\s*\n\s*}\s*\n\s*\]\s*\n)', f'"name": "#{ep_num} {title}"\\1', html)

    # --- article-hero ---
    # エピソード番号
    html = re.sub(r'<span>#\d+</span>', f'<span>#{ep_num}</span>', html)
    # 日付
    html = re.sub(r'<span>\d{4}\.\d{2}\.\d{2}</span>', f'<span>{today_dot}</span>', html)
    # tier badge
    tier_label = "FREE" if tier == "free" else "PRO"
    html = re.sub(r'<span class="episode-badge">[^<]*</span>', f'<span class="episode-badge">{tier_label}</span>', html)
    # h1タイトル
    html = re.sub(r'<h1>[^<]*</h1>', f'<h1>{title}</h1>', html)
    # lead文
    html = re.sub(r'<p class="lead">[^<]*</p>', f'<p class="lead">{desc_safe}</p>', html)

    # タグ
    tags_html = "\n".join(f'        <span class="tag">{tag}</span>' for tag in tags)
    html = re.sub(
        r'<div class="article-tags">.*?</div>',
        f'<div class="article-tags">\n{tags_html}\n      </div>',
        html,
        flags=re.DOTALL,
    )

    # --- 音声プレーヤー ---
    html = re.sub(r'data-audio="[^"]*"', f'data-audio="https://audio.deepcast-ai.com/{ep_str}.mp3"', html)
    html = re.sub(r'data-title="[^"]*"', f'data-title="{title}"', html)

    # --- article-body の中身を置換 ---
    html = re.sub(
        r'(<div class="article-body">).*?(<div class="article-share">)',
        rf'\1\n\n{article_html}\n    \2',
        html,
        flags=re.DOTALL,
    )

    # カテゴリ表示
    html = re.sub(r'<span>社会・倫理</span>', '<span>テクノロジー</span>', html)

    out_path = EPISODES_DIR / f"{ep_str}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main():
    print("=" * 60)
    print("DeepCast テキストのみエピソード生成")
    print("音声生成・R2アップロードはスキップ")
    print("=" * 60)

    # テンプレート読み込み
    template_path = EPISODES_DIR / "ep001.html"
    if template_path.exists():
        template_html = template_path.read_text(encoding="utf-8")
        print(f"テンプレート読み込み完了: {template_path} ({len(template_html)}文字)")
    else:
        print("ERROR: テンプレートファイル ep001.html が見つかりません")
        sys.exit(1)

    # episodes.jsonをリセット
    episodes_list = []

    total = len(NEW_TOPICS)
    print(f"\n生成対象: {total}本")
    print(f"  Free: ep008〜ep010 (最新3本)")
    print(f"  Pro:  ep001〜ep007 (残り7本)")

    generated = 0

    for i, topic_title in enumerate(NEW_TOPICS):
        ep_num = i + 1
        ep_str = f"ep{ep_num:03d}"

        # Free/Pro判定: ep008-010がfree、ep001-007がpro
        tier = "free" if ep_num >= 8 else "pro"

        print(f"\n{'='*60}")
        print(f"[{ep_str}] ({i+1}/{total}) {topic_title} [{tier.upper()}]")
        print(f"{'='*60}")

        try:
            # 1. コンテンツ生成
            print("  [1/3] コンテンツ生成中...")
            body = generate_content(topic_title)

            # 説明文を生成（本文先頭から抽出）
            # マークダウン見出しを除外した本文部分から説明を生成
            plain_lines = [l for l in body.split("\n") if l.strip() and not l.strip().startswith("#")]
            description = " ".join(plain_lines)[:200].strip()
            if len(description) > 150:
                description = description[:150] + "..."

            # タグ生成
            tags = []
            for word in topic_title.replace("—", " ").replace("―", " ").replace("「", " ").replace("」", " ").split():
                word = word.strip()
                if len(word) > 1 and word not in tags:
                    tags.append(word)
                if len(tags) >= 4:
                    break

            # 2. HTML生成
            print("  [2/3] HTMLページ生成中...")
            html_path = create_episode_html(
                ep_num=ep_num,
                title=topic_title,
                body=body,
                description=description,
                tier=tier,
                tags=tags,
                template=template_html,
            )
            print(f"    -> {html_path}")

            # 3. episodes.jsonにエントリ追加
            print("  [3/3] episodes.jsonエントリ作成中...")
            today_dot = datetime.now().strftime("%Y.%m.%d")
            entry = {
                "id": ep_num,
                "title": topic_title,
                "description": description,
                "date": today_dot,
                "category": "tech",
                "tags": tags,
                "duration": "2:30",
                "audio": "",
                "article": f"episodes/{ep_str}.html",
                "language": "ja",
                "tier": tier,
            }
            episodes_list.append(entry)

            print(f"  [DONE] {ep_str}: {topic_title} [{tier.upper()}]")
            generated += 1

        except Exception as e:
            print(f"  [ERROR] {topic_title}: {e}")
            traceback.print_exc()
            continue

    # episodes.jsonを書き出し（新しい順 = id降順）
    episodes_list.sort(key=lambda x: x["id"], reverse=True)
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodes_list, f, ensure_ascii=False, indent=2)
    print(f"\nepisodes.json書き出し完了: {len(episodes_list)}件")

    # 結果サマリー
    print(f"\n{'='*60}")
    print(f"完了: {generated}/{total}本生成")
    print(f"{'='*60}")

    for ep in episodes_list:
        print(f"  #{ep['id']:03d} [{ep['tier'].upper():4s}] {ep['title']}")


if __name__ == "__main__":
    main()
