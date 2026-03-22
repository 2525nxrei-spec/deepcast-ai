#!/usr/bin/env python3
"""
DeepCast Production Cleanup & Publish Script
- Step 1: Clean up test data
- Step 2: Publish 5 quality episodes
- Step 3: Generate audio via edge-tts
- Step 4: Verify everything
"""

import os
import sys
import json
import sqlite3
import shutil
import asyncio
import re
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────
# PATHS（環境変数 or settings.py から取得、ハードコードしない）
# ──────────────────────────────────────────
try:
    from config.settings import settings as _settings
    SITE_DIR = Path(_settings.SITE_ROOT)
except ImportError:
    SITE_DIR = Path(os.environ.get("SITE_ROOT", str(Path(__file__).resolve().parent.parent)))
ENGINE_DIR = SITE_DIR / "engine"
EPISODES_DIR = SITE_DIR / "episodes"
DB_PATH = ENGINE_DIR / "data" / "deepcast.db"
AUDIO_SRC_DIR = ENGINE_DIR / "data" / "audio"

TODAY = "2026-03-17"
TODAY_DOT = "2026.03.17"

# ══════════════════════════════════════════
# STEP 1: CLEAN UP TEST DATA
# ══════════════════════════════════════════
def step1_cleanup():
    print("\n" + "="*60)
    print("STEP 1: CLEAN UP TEST DATA")
    print("="*60)

    # 1a. Delete ep004.html (test)
    ep004 = EPISODES_DIR / "ep004.html"
    if ep004.exists():
        ep004.unlink()
        print(f"  [OK] Deleted {ep004}")
    else:
        print(f"  [SKIP] {ep004} not found")

    # 1b. Remove id=4 from episodes.json
    ej_path = EPISODES_DIR / "episodes.json"
    with open(ej_path, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    before = len(episodes)
    episodes = [e for e in episodes if e.get("id") != 4]
    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)
    print(f"  [OK] episodes.json: {before} -> {len(episodes)} entries (removed id=4)")

    # 1c. Remove ep004 from sitemap.xml
    sm_path = SITE_DIR / "sitemap.xml"
    with open(sm_path, "r", encoding="utf-8") as f:
        sitemap = f.read()
    # Remove the <url> block containing ep004
    sitemap_new = re.sub(
        r'\s*<url>\s*<loc>https://deepcast-ai\.com/episodes/ep004\.html</loc>.*?</url>',
        '', sitemap, flags=re.DOTALL
    )
    with open(sm_path, "w", encoding="utf-8") as f:
        f.write(sitemap_new)
    print(f"  [OK] sitemap.xml: removed ep004 entry")

    # 1d. Remove ep004 from feed.xml
    feed_path = SITE_DIR / "feed.xml"
    with open(feed_path, "r", encoding="utf-8") as f:
        feed = f.read()
    # Remove the <item> block containing ep004
    feed_new = re.sub(
        r'\s*<item>\s*<title>#4[^<]*</title>.*?</item>',
        '', feed, flags=re.DOTALL
    )
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(feed_new)
    print(f"  [OK] feed.xml: removed ep004 item")

    # 1e. Delete test_en.mp3
    test_mp3 = AUDIO_SRC_DIR / "test_en.mp3"
    if test_mp3.exists():
        test_mp3.unlink()
        print(f"  [OK] Deleted {test_mp3}")
    else:
        print(f"  [SKIP] {test_mp3} not found")

    # 1f/g. Delete DB entries ID 1, 2, 4
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    for rid in [1, 2, 4]:
        c.execute("DELETE FROM contents WHERE id = ?", (rid,))
        c.execute("DELETE FROM quality_logs WHERE content_id = ?", (rid,))
        print(f"  [OK] Deleted DB content ID={rid}")
    conn.commit()

    # Verify remaining
    c.execute("SELECT id, title, language, quality_score, status FROM contents ORDER BY id")
    remaining = c.fetchall()
    print(f"\n  Remaining DB contents ({len(remaining)}):")
    for r in remaining:
        print(f"    ID={r[0]} | {r[2]} | Score={r[3]} | {r[4]} | {r[1][:50]}")
    conn.close()


# ══════════════════════════════════════════
# STEP 2 & 3: PUBLISH EPISODES + AUDIO
# ══════════════════════════════════════════

# Episode definitions
# DB IDs 3, 5, 6 + 2 new generated ones
EPISODE_PLAN = [
    # (ep_num, html_file, audio_file, db_id_or_None, lang, title, description, category, tags, body_override)
    # ep004 - DB ID 3 (ja, Sustainable Finance)
    {
        "ep_num": 4, "html": "ep004.html", "audio": "ep024.mp3",
        "db_id": 3, "lang": "ja",
        "title": "サステナブルファイナンスの台頭 — ESG投資と企業の社会的責任",
        "description": "ESG投資が世界の金融を変えつつある。環境・社会・ガバナンスの視点から、持続可能な経済のあり方を読み解く。",
        "category": "経済",
        "tags": ["ESG投資", "サステナブル", "企業倫理"],
        "keywords": "ESG投資,サステナブルファイナンス,企業の社会的責任,持続可能な経済",
        "audio_src": "ja_3_202603171955.mp3",
        "body": None,  # will be extracted from DB
    },
    # ep005 - DB ID 5 (ja, Sustainable Finance: A New Era)
    {
        "ep_num": 5, "html": "ep005.html", "audio": "ep025.mp3",
        "db_id": 5, "lang": "ja",
        "title": "投資の新時代 — ESGが拓くサステナブルファイナンスの未来",
        "description": "ESG投資が急成長する今、投資家と企業は何を変えるべきか。持続可能な金融の全体像と実践方法を解説。",
        "category": "経済",
        "tags": ["ESG投資", "サステナブル", "金融イノベーション"],
        "keywords": "ESG投資,サステナブルファイナンス,持続可能な金融,企業の社会的責任",
        "audio_src": "ja_5_202603171955.mp3",
        "body": None,
    },
    # ep006 - DB ID 6 (en, Economics of Climate Change)
    {
        "ep_num": 6, "html": "ep006.html", "audio": "ep026.mp3",
        "db_id": 6, "lang": "en",
        "title": "The Economics of Climate Change — A Global Perspective",
        "description": "What does climate change cost the global economy, and what does action look like? Carbon pricing, green infrastructure, and the path forward.",
        "category": "Economy",
        "tags": ["Climate Change", "Sustainability", "Carbon Pricing"],
        "keywords": "climate change,global economy,sustainability,carbon pricing",
        "audio_src": "en_6_202603171955.mp3",
        "body": None,
    },
    # ep007 - NEW (ja, AIが変える教育の未来)
    {
        "ep_num": 7, "html": "ep007.html", "audio": "ep027.mp3",
        "db_id": None, "lang": "ja",
        "title": "AIが変える教育の未来 — EdTech革命の最前線",
        "description": "AIが教育をどう変えるのか。個別最適化学習、教師の役割変化、EdTechスタートアップの最新動向を多角的に分析。",
        "category": "テクノロジー",
        "tags": ["AI", "教育", "EdTech"],
        "keywords": "AI教育,EdTech,個別最適化学習,教育イノベーション,アダプティブラーニング",
        "audio_src": None,  # will generate
        "body": """<h2>はじめに — 教育はAIでどう変わるのか</h2>
    <p>2026年、教育の風景は急速に変貌を遂げている。<strong>生成AI</strong>の爆発的な普及は、知識の伝達方法そのものを根本から問い直す契機となった。かつて教室で教師が一方的に知識を伝える「一斉授業」が主流だった時代は過ぎ去り、AIが各生徒の理解度・興味・学習速度に応じて最適なカリキュラムを動的に生成する<strong>「個別最適化学習（Adaptive Learning）」</strong>が現実のものとなっている。</p>
    <p>本エピソードでは、AIが教育に与えるインパクトを<strong>テクノロジー・教育学・社会制度</strong>の三つの軸から多角的に分析し、EdTech革命の最前線を読み解いていく。</p>

    <h2>個別最適化学習の実現 — 一人ひとりに「最適な教師」を</h2>
    <h3>アダプティブラーニングの仕組み</h3>
    <p>アダプティブラーニングとは、<strong>学習者のパフォーマンスデータをリアルタイムで分析し、次に提示すべき教材の難易度・形式・順序を自動調整する技術</strong>である。従来のeラーニングが固定的なコンテンツを順番に提示するのに対し、アダプティブラーニングは学習者の「つまずきポイント」を即座に検出し、補助教材や別角度からの説明を自動挿入する。</p>
    <p>例えば、数学の二次方程式を学ぶ生徒が因数分解で躓いた場合、AIは因数分解の基礎に遡るミニレッスンを自動生成し、理解が確認されてから元のカリキュラムに復帰させる。この「<strong>マイクロ介入</strong>」が、従来の教室では物理的に不可能だった30人30通りの指導を実現する。</p>

    <h3>大規模言語モデルが変えた「質問と対話」</h3>
    <p>GPT系モデルやGeminiに代表される大規模言語モデル（LLM）の登場により、学習者は<strong>24時間365日、あらゆる質問に自然言語で回答してくれる「AIチューター」</strong>を手に入れた。重要なのは、これが単なるFAQボットではなく、ソクラテス式の問いかけで思考を深める対話型の学習支援を提供できることだ。</p>
    <p>スタンフォード大学の研究チームが2025年に発表した論文によれば、AIチューターを活用した学生群は、従来の講義のみの群と比較して<strong>テストスコアが平均17%向上</strong>し、学習への主観的満足度も有意に高かった。</p>

    <div class="highlight-box">
      <h4>AIチューターの主な利点</h4>
      <ul>
        <li><strong>即時フィードバック</strong> — 回答の正誤だけでなく、思考プロセスの改善点を提示</li>
        <li><strong>無制限の忍耐</strong> — 何度同じ質問をしても感情的にならない</li>
        <li><strong>多言語対応</strong> — 母語が異なる学習者にも自然な言語で対応</li>
        <li><strong>学習ログの蓄積</strong> — 長期的な成長曲線を可視化し、メタ認知を促進</li>
      </ul>
    </div>

    <h2>教師の役割はどう変わるのか</h2>
    <h3>「知識の伝達者」から「学びのデザイナー」へ</h3>
    <p>AIが知識伝達と反復練習を効率的に担うようになると、教師の役割は劇的に変化する。<strong>教師は「情報を教える人」から「学びの経験をデザインし、生徒の動機づけと社会性の発達を支援するファシリテーター」</strong>へと進化する。</p>
    <p>フィンランドの教育改革を研究するパシ・サルバーグは、AIの時代にこそ教師の「<strong>人間的な関わり</strong>」の価値が増大すると指摘する。AIは知識を教えられるが、挫折した生徒に寄り添い、内発的動機を引き出し、協働プロジェクトを通じて社会性を育むことは人間の教師にしかできない。</p>

    <h3>データドリブンな指導の実現</h3>
    <p>AIは教師に強力な<strong>「教育ダッシュボード」</strong>を提供する。クラス全体の理解度分布、個々の生徒の学習パターン、つまずきの頻出箇所がリアルタイムで可視化される。これにより、教師は<strong>「勘と経験」だけでなく「データに基づいた科学的な指導判断」</strong>を下せるようになる。</p>

    <h2>EdTechスタートアップの最新動向</h2>
    <h3>注目すべき4つの領域</h3>
    <p>2026年のEdTech市場は、以下の4領域で特に革新が進んでいる。</p>

    <div class="highlight-box">
      <h4>EdTech注目4領域</h4>
      <ul>
        <li><strong>AIチューター・プラットフォーム</strong> — Khanmigo、Duolingo Max、Photomath AIなど、個別指導AIの精度が飛躍的に向上</li>
        <li><strong>没入型学習（XR教育）</strong> — VR/ARを活用した体験型学習。歴史の現場を「歩く」、分子構造を「触る」</li>
        <li><strong>スキルベース認証</strong> — 学歴ではなく実際のスキルを証明するマイクロクレデンシャルの普及</li>
        <li><strong>グローバル学習マーケットプレイス</strong> — 国境を越えた教師と学習者のマッチング</li>
      </ul>
    </div>

    <h2>課題と懸念 — 光の裏にある影</h2>
    <h3>デジタルデバイドの深刻化</h3>
    <p>AIを活用した最先端の教育ツールが普及する一方で、<strong>インターネット接続やデバイスへのアクセスが限られる地域・家庭</strong>との格差は拡大する懸念がある。EdTechの恩恵が富裕層に偏れば、教育格差は縮まるどころかむしろ拡大する。</p>

    <h3>思考力の外部委託リスク</h3>
    <p>AIに「答え」を聞けば数秒で回答が返ってくる環境は、便利である反面、<strong>自ら考え抜く力、粘り強く試行錯誤する力</strong>を減退させるリスクをはらむ。「分からない」という不快な状態に耐え、自力で突破口を見つける経験こそが深い学びの本質であり、AIがこのプロセスを短絡させてしまう危険性を多くの教育学者が警告している。</p>

    <h3>プライバシーとデータ倫理</h3>
    <p>学習データの収集・分析は教育の質を向上させる一方で、<strong>子どものプライバシー保護</strong>という重大な倫理的課題を伴う。学習ログ、行動パターン、感情分析データなどが蓄積されることで、将来の進路や就職に影響を与える「<strong>教育スコアリング</strong>」への懸念も浮上している。</p>

    <h2>未来への展望 — 人間とAIの共進化</h2>
    <p>AIが教育を変革することは不可避の流れだ。しかし、その方向性を決めるのは技術ではなく<strong>人間の意思</strong>である。テクノロジーを「効率化の道具」としてのみ捉えるのか、それとも「すべての人に質の高い学びを届ける社会インフラ」として位置づけるのか——この選択が、次の10年の教育を決定づける。</p>
    <p><strong>AIは教師を代替するのではなく、教師を「拡張」する。</strong>一人の教師が30人の生徒それぞれに最適な学びを届けることは、人間だけでは不可能だった。AIというパートナーを得ることで、教育は初めて真の意味で「個」に向き合えるようになる。</p>
    <p>EdTech革命の最前線は、テクノロジーと人間性が交差する場所にある。私たちに求められるのは、AIの可能性を最大限に引き出しながら、教育の本質——<strong>人が人として成長すること</strong>——を決して見失わない姿勢だ。</p>""",
    },
    # ep008 - NEW (en, Psychology of Decision Making)
    {
        "ep_num": 8, "html": "ep008.html", "audio": "ep028.mp3",
        "db_id": None, "lang": "en",
        "title": "The Psychology of Decision Making in the Age of AI",
        "description": "How does AI reshape human decision-making? From cognitive biases to algorithmic nudges, an exploration of choice architecture in the AI era.",
        "category": "Psychology",
        "tags": ["Psychology", "AI", "Decision Making"],
        "keywords": "decision making,cognitive bias,AI,behavioral economics,choice architecture,nudge theory",
        "audio_src": None,
        "body": """<h2>Introduction: The Paradox of Choice in an AI-Mediated World</h2>
    <p>Every day, the average person makes approximately <strong>35,000 decisions</strong>. From the mundane — what to eat for breakfast — to the consequential — whether to accept a job offer — our cognitive machinery is perpetually engaged in the act of choosing. But what happens when artificial intelligence begins to mediate, influence, and even preempt many of these decisions?</p>
    <p>We live in an era where recommendation algorithms curate our newsfeeds, predictive models suggest our next purchase, and AI assistants schedule our calendars. The question is no longer whether AI affects our decision-making, but <strong>how deeply it has already reshaped the architecture of human choice</strong>.</p>
    <p>This episode explores the intersection of cognitive psychology, behavioral economics, and artificial intelligence to understand how the age of AI is fundamentally transforming the way we think, choose, and act.</p>

    <h2>The Cognitive Foundations of Decision Making</h2>
    <h3>System 1 and System 2: Kahneman's Dual-Process Theory</h3>
    <p>Nobel laureate Daniel Kahneman's seminal framework distinguishes between two modes of thinking. <strong>System 1</strong> is fast, automatic, and intuitive — the mental process that allows you to recognize a friend's face or dodge an oncoming obstacle. <strong>System 2</strong> is slow, deliberate, and analytical — the mode engaged when solving a complex math problem or comparing insurance policies.</p>
    <p>Most of our daily decisions rely on System 1, which, while efficient, is susceptible to a host of <strong>cognitive biases</strong>: anchoring effects, availability heuristics, confirmation bias, and loss aversion, to name a few. These systematic errors in judgment have been extensively documented over the past five decades of psychological research.</p>
    <p>The critical insight is this: <strong>AI systems are increasingly designed to interact with — and exploit — our System 1 processes.</strong> Recommendation engines, notification systems, and auto-complete features all target the fast, intuitive brain, often bypassing our more reflective analytical capacities.</p>

    <h3>Bounded Rationality and Satisficing</h3>
    <p>Herbert Simon's concept of <strong>bounded rationality</strong> recognizes that human decision-makers operate within constraints: limited information, limited time, and limited cognitive capacity. Rather than optimizing — finding the absolute best option — we typically <strong>satisfice</strong>, choosing the first option that meets a minimum threshold of acceptability.</p>
    <p>AI promises to expand these bounds. With access to vast datasets and computational power, AI systems can process information far beyond human capacity. But does this expansion of analytical power actually lead to better decisions? The evidence is more nuanced than one might expect.</p>

    <div class="highlight-box">
      <h4>Key Cognitive Biases Amplified by AI</h4>
      <ul>
        <li><strong>Automation Bias</strong> — The tendency to favor suggestions from automated systems over contradictory information from non-automated sources</li>
        <li><strong>Anchoring Effect</strong> — AI-generated initial estimates become powerful anchors that skew subsequent human judgment</li>
        <li><strong>Confirmation Bias</strong> — Recommendation algorithms create filter bubbles that reinforce existing beliefs</li>
        <li><strong>Availability Heuristic</strong> — AI-curated content distorts our perception of event frequency and importance</li>
      </ul>
    </div>

    <h2>The Architecture of AI-Mediated Choice</h2>
    <h3>Nudge Theory Meets Machine Learning</h3>
    <p>Richard Thaler and Cass Sunstein's <strong>nudge theory</strong> proposed that the design of choice environments — the "choice architecture" — profoundly influences decisions without restricting options. A cafeteria that places healthy foods at eye level nudges diners toward better choices without removing the option of less healthy alternatives.</p>
    <p>AI has supercharged this concept. Modern choice architecture is no longer static — it is <strong>dynamically personalized</strong>. Netflix doesn't just recommend popular shows; it tailors thumbnails, descriptions, and ordering to each individual user's predicted preferences. Spotify's Discover Weekly doesn't just suggest music; it constructs a narrative of musical exploration calibrated to your evolving taste profile.</p>
    <p>The implications are profound. When the choice environment itself is personalized by an algorithm that knows your behavioral patterns better than you do, <strong>the boundary between "choosing" and "being chosen for" begins to blur</strong>.</p>

    <h3>The Delegation Spectrum</h3>
    <p>Human-AI decision interaction exists on a spectrum. At one end lies <strong>full human autonomy</strong> — the AI provides raw data, and the human decides. At the other end lies <strong>full automation</strong> — the AI decides and acts without human input. Between these poles exists a range of collaborative models:</p>
    <p><strong>AI as Advisor</strong>: The system provides recommendations, but humans retain final authority. Medical diagnostic AI and financial advisory tools typically operate here.</p>
    <p><strong>AI as Gatekeeper</strong>: The system filters and pre-selects options before presenting them to human decision-makers. Search engines and hiring algorithms occupy this space.</p>
    <p><strong>AI as Autopilot</strong>: The system acts autonomously within defined parameters, with humans monitoring and intervening when necessary. Self-driving vehicles and algorithmic trading exemplify this model.</p>
    <p>Each point on this spectrum involves distinct psychological dynamics, ethical considerations, and failure modes.</p>

    <h2>The Dark Patterns: When AI Exploits Cognitive Vulnerability</h2>
    <h3>Attention Hijacking</h3>
    <p>The attention economy has created perverse incentives for AI systems to <strong>maximize engagement rather than maximize user welfare</strong>. Social media algorithms have been optimized for metrics like time-on-platform and click-through rates, which often correlate with content that triggers outrage, anxiety, or addictive scrolling patterns.</p>
    <p>Tristan Harris, former design ethicist at Google, has argued that these systems exploit fundamental psychological vulnerabilities — our need for social approval (variable reward schedules in notifications), our fear of missing out (urgency-inducing design), and our negativity bias (algorithmic amplification of emotionally charged content).</p>

    <h3>The Paradox of Personalization</h3>
    <p>Personalization promises relevance but delivers a subtle form of intellectual confinement. When every piece of information you encounter has been selected by an algorithm predicting what you want to see, <strong>you lose exposure to the serendipitous, the challenging, and the genuinely novel</strong>. Eli Pariser's concept of the "filter bubble" has only grown more relevant as personalization algorithms have become more sophisticated.</p>
    <p>Research from MIT's Media Lab demonstrates that individuals exposed to algorithmically curated newsfeeds show <strong>measurably reduced cognitive flexibility</strong> compared to those who encounter information through more diverse channels. The algorithm optimizes for immediate satisfaction but may undermine long-term intellectual growth.</p>

    <div class="highlight-box">
      <h4>Signs of AI-Influenced Decision Fatigue</h4>
      <ul>
        <li><strong>Decision Outsourcing</strong> — Defaulting to AI recommendations without conscious evaluation</li>
        <li><strong>Paradox of Choice Escalation</strong> — AI-generated options overwhelm rather than simplify</li>
        <li><strong>Reduced Metacognition</strong> — Declining awareness of one's own decision-making processes</li>
        <li><strong>Preference Ossification</strong> — Algorithmic reinforcement of existing preferences prevents exploration</li>
      </ul>
    </div>

    <h2>Reclaiming Agency: Strategies for Autonomous Decision Making</h2>
    <h3>Cognitive Debiasing in the AI Age</h3>
    <p>The first step toward reclaiming decision-making agency is <strong>metacognitive awareness</strong> — understanding how our own cognitive processes work and how AI systems interact with them. This doesn't mean rejecting AI assistance entirely, but rather developing the capacity to critically evaluate AI recommendations.</p>
    <p>Several evidence-based strategies can help:</p>
    <p><strong>Deliberate Friction</strong>: Intentionally introducing delays or additional steps before accepting AI recommendations. Research shows that even a five-second pause before clicking a recommended link significantly increases the probability of a deliberate, rather than impulsive, choice.</p>
    <p><strong>Adversarial Thinking</strong>: Actively seeking information that contradicts AI recommendations. If Spotify suggests a playlist, deliberately exploring music outside that recommendation. If a news algorithm prioritizes certain stories, intentionally seeking alternative perspectives.</p>
    <p><strong>Decision Journaling</strong>: Maintaining a record of significant decisions — including which were AI-influenced — and their outcomes. This practice strengthens metacognitive skills and reveals patterns of over-reliance on algorithmic guidance.</p>

    <h3>Designing Ethical Choice Architecture</h3>
    <p>The responsibility for ethical AI-mediated decision environments doesn't rest solely on individuals. System designers, policymakers, and organizations must prioritize <strong>transparency, autonomy preservation, and genuine user welfare</strong> over engagement metrics.</p>
    <p>The European Union's AI Act represents an important step, requiring that AI systems designed to influence human behavior disclose their nature and intent. But regulation alone is insufficient. We need a <strong>cultural shift</strong> that values cognitive autonomy as a fundamental human right.</p>

    <h2>Conclusion: The Conscious Chooser</h2>
    <p>The age of AI presents a profound paradox for human decision-making. We have access to more information, more analysis, and more predictive power than at any point in history — yet the risk of losing our capacity for autonomous, reflective choice has never been greater.</p>
    <p>The path forward is not Luddite rejection of AI, nor is it uncritical surrender to algorithmic guidance. It is the cultivation of what we might call <strong>"conscious choosing"</strong> — the deliberate practice of engaging both our intuitive and analytical faculties, leveraging AI as a tool while maintaining awareness of its influence on our cognitive processes.</p>
    <p>In the words of psychologist Barry Schwartz, "The secret to happiness is <strong>low expectations</strong>." Perhaps the secret to good decision-making in the AI age is something similar: not expecting AI to make our choices for us, but expecting it to illuminate the landscape of choice so that we can navigate it with greater wisdom, awareness, and intentionality.</p>
    <p>The 35,000 decisions you make today will be influenced by artificial intelligence in ways both visible and invisible. The most important decision of all may be this: <strong>to remain conscious of how you choose.</strong></p>""",
    },
]


def get_db_body(db_id):
    """Extract body from DB and convert markdown-style to HTML."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT body, language FROM contents WHERE id = ?", (db_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return "", "ja"
    body, lang = row
    # Convert markdown-ish to HTML
    html_parts = []
    lines = body.strip().split("\n")
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("#### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3>{line[5:]}</h3>")
        elif line.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2>{line[2:]}</h2>")
        elif line.startswith("**") and line.endswith("**") and len(line) < 100:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Bold heading-like
            html_parts.append(f"<h3>{line[2:-2]}</h3>")
        elif line.startswith("* ") or line.startswith("- "):
            if not in_list:
                html_parts.append('<div class="highlight-box"><ul>')
                in_list = True
            content = line[2:]
            # convert **text** to <strong>
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_parts.append(f"<li>{content}</li>")
        else:
            if in_list:
                html_parts.append("</ul></div>")
                in_list = False
            # Process inline bold
            processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            # Skip lines that are just metadata
            if processed.startswith("**Estimated Read Time") or processed.startswith("**Summary"):
                continue
            if processed.startswith("**Tags"):
                continue
            if processed.startswith("**Category"):
                continue
            if processed.startswith("**SEO Keywords"):
                continue
            html_parts.append(f"<p>{processed}</p>")
    if in_list:
        html_parts.append("</ul></div>")
    return "\n    ".join(html_parts), lang


def generate_episode_html(ep):
    """Generate a full episode HTML page following the ep001.html template."""
    lang = ep["lang"]
    ep_num = ep["ep_num"]
    is_ja = lang == "ja"

    # Get body
    if ep["body"]:
        body_html = ep["body"]
    else:
        body_html, _ = get_db_body(ep["db_id"])

    locale = "ja_JP" if is_ja else "en_US"
    back_text = "エピソード一覧に戻る" if is_ja else "Back to All Episodes"
    listen_text = "音声で聴く" if is_ja else "Listen"
    share_text = "このエピソードをシェアする" if is_ja else "Share this episode"
    more_text = "他のエピソードも聴く" if is_ja else "Listen to more episodes"
    ep_list_text = "エピソード一覧" if is_ja else "All Episodes"
    menu_label = "メニュー" if is_ja else "Menu"
    play_label = "再生" if is_ja else "Play"

    # Nav links
    if is_ja:
        nav_links = """<li><a href="../#episodes">エピソード</a></li>
        <li><a href="../#request">リクエスト</a></li>
        <li><a href="../#services">サービス</a></li>
        <li><a href="../#faq">FAQ</a></li>"""
        nav_btn = f'<a href="../all-episodes.html" class="btn btn-primary btn-sm">エピソードを聴く</a>'
    else:
        nav_links = """<li><a href="../#episodes">Episodes</a></li>
        <li><a href="../#request">Request</a></li>
        <li><a href="../#services">Services</a></li>
        <li><a href="../#faq">FAQ</a></li>"""
        nav_btn = f'<a href="../all-episodes.html" class="btn btn-primary btn-sm">Listen Now</a>'

    # Footer
    if is_ja:
        footer_desc = "AIが生み出す、5分間の深い洞察。<br>あなたの知識を毎日アップデート。"
        footer_svc = "サービス"
        footer_ep = "エピソード一覧"
        footer_req = "トピックリクエスト"
        footer_legal = "法的情報"
    else:
        footer_desc = "5-minute deep insights powered by AI.<br>Update your knowledge daily."
        footer_svc = "Services"
        footer_ep = "All Episodes"
        footer_req = "Topic Requests"
        footer_legal = "Legal"

    tags_html = "\n        ".join(f'<span class="tag">{t}</span>' for t in ep["tags"])

    html = f'''<!DOCTYPE html>
<html lang="{lang}">
<head>
  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-NRM2K26K7J"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-NRM2K26K7J');
  </script>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>#{ep_num} {ep["title"]}&#xFF5C;DeepCast AI</title>
  <meta name="description" content="{ep["description"]}">
  <meta name="keywords" content="{ep["keywords"]}">
  <link rel="canonical" href="https://deepcast-ai.com/episodes/{ep["html"]}">
  <meta property="og:title" content="#{ep_num} {ep["title"]}&#xFF5C;DeepCast AI">
  <meta property="og:description" content="{ep["description"]}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://deepcast-ai.com/episodes/{ep["html"]}">
  <meta property="og:image" content="https://deepcast-ai.com/assets/cover-ep{ep_num:03d}.svg">
  <meta property="og:site_name" content="DeepCast AI">
  <meta property="og:locale" content="{locale}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="#{ep_num} {ep["title"]}&#xFF5C;DeepCast AI">
  <meta name="twitter:description" content="{ep["description"]}">
  <meta name="twitter:image" content="https://deepcast-ai.com/assets/cover-ep{ep_num:03d}.svg">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="../assets/icon.svg">
  <link rel="stylesheet" href="../css/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Serif+JP:wght@400;600;700&display=swap" rel="stylesheet">
  <script type="application/ld+json">
  [
    {{
      "@context": "https://schema.org",
      "@type": "PodcastEpisode",
      "name": "{ep["title"]}",
      "description": "{ep["description"]}",
      "datePublished": "{TODAY}",
      "duration": "PT5M",
      "episodeNumber": {ep_num},
      "url": "https://deepcast-ai.com/episodes/{ep["html"]}",
      "associatedMedia": {{
        "@type": "MediaObject",
        "contentUrl": "https://deepcast-ai.com/episodes/{ep["audio"]}"
      }},
      "partOfSeries": {{
        "@type": "PodcastSeries",
        "name": "DeepCast AI",
        "url": "https://deepcast-ai.com/"
      }}
    }},
    {{
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      "itemListElement": [
        {{"@type": "ListItem", "position": 1, "name": "DeepCast AI", "item": "https://deepcast-ai.com/"}},
        {{"@type": "ListItem", "position": 2, "name": "{ep_list_text}", "item": "https://deepcast-ai.com/all-episodes.html"}},
        {{"@type": "ListItem", "position": 3, "name": "#{ep_num} {ep["title"]}"}}
      ]
    }}
  ]
  </script>
  <style>
    .article-hero {{
      padding: 100px 24px 40px;
      background: var(--bg);
    }}
    .article-hero .container {{ max-width: 760px; margin: 0 auto; }}
    .article-meta {{
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
      margin-bottom: 16px; font-size: 12px; color: var(--text-muted);
    }}
    .article-meta .episode-badge {{ padding: 2px 9px; border-radius: var(--radius-full); font-size: 10px; font-weight: 600; background: rgba(94, 194, 105, 0.1); color: var(--green); }}
    .article-hero h1 {{
      font-family: var(--serif);
      font-size: clamp(24px, 4vw, 36px);
      font-weight: 700; line-height: 1.4;
      letter-spacing: -0.02em;
      margin-bottom: 12px;
    }}
    .article-hero .lead {{
      font-size: 15px; color: var(--text-secondary); line-height: 1.8;
    }}
    .article-player-bar {{
      max-width: 760px; margin: 0 auto 32px;
      padding: 16px 24px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      display: flex; align-items: center; gap: 12px;
    }}
    .article-body {{
      max-width: 760px; margin: 0 auto;
      padding: 0 24px 72px;
    }}
    .article-body h2 {{
      font-family: var(--serif);
      font-size: 22px; font-weight: 700;
      margin: 48px 0 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }}
    .article-body h3 {{
      font-size: 17px; font-weight: 600;
      margin: 32px 0 12px;
    }}
    .article-body p {{
      font-size: 15px; line-height: 1.9;
      color: var(--text-secondary);
      margin-bottom: 16px;
    }}
    .article-body strong {{ color: var(--text); }}
    .article-body .highlight-box {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px 24px;
      margin: 24px 0;
    }}
    .article-body .highlight-box h4 {{
      font-size: 14px; font-weight: 600;
      margin-bottom: 8px; color: var(--text);
    }}
    .article-body .highlight-box ul {{
      list-style: none; padding: 0; margin: 0;
    }}
    .article-body .highlight-box li {{
      font-size: 14px; line-height: 1.7;
      color: var(--text-secondary);
      padding: 4px 0 4px 16px;
      position: relative;
    }}
    .article-body .highlight-box li::before {{
      content: "\\2014"; position: absolute; left: 0; color: var(--text-muted);
    }}
    .article-back {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 13px; color: var(--text-muted);
      margin-bottom: 24px;
      transition: color 0.2s;
    }}
    .article-back:hover {{ color: var(--text); }}
    .article-tags {{ display: flex; gap: 6px; margin-top: 8px; }}
    .article-share {{
      margin-top: 48px; padding-top: 24px;
      border-top: 1px solid var(--border);
      text-align: center;
    }}
    .article-share p {{ font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }}
  </style>
</head>
<body>
  <!-- NAVIGATION -->
  <nav class="navbar scrolled" id="navbar">
    <div class="container nav-container">
      <a href="../" class="logo">
        <span class="logo-icon">&#9678;</span>
        <span class="logo-text">DeepCast<span class="logo-ai">AI</span></span>
      </a>
      <ul class="nav-links" id="navLinks">
        {nav_links}
      </ul>
      <div class="nav-actions">
        {nav_btn}
      </div>
      <button class="hamburger" id="hamburger" aria-label="{menu_label}">
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>

  <!-- ARTICLE HERO -->
  <div class="article-hero">
    <div class="container">
      <a href="../all-episodes.html" class="article-back">&larr; {back_text}</a>
      <div class="article-meta">
        <span class="episode-badge">FREE</span>
        <span>#{ep_num}</span>
        <span>{TODAY_DOT}</span>
        <span>{ep["category"]}</span>
        <span>5:00</span>
      </div>
      <h1>{ep["title"]}</h1>
      <p class="lead">{ep["description"]}</p>
      <div class="article-tags">
        {tags_html}
      </div>
    </div>
  </div>

  <!-- INLINE PLAYER -->
  <div class="article-player-bar">
    <button class="play-btn" id="articlePlayBtn" data-audio="../episodes/{ep["audio"]}" data-title="{ep["title"]}" aria-label="{play_label}">
      <span class="play-icon">&#9654;</span>
    </button>
    <div class="episode-progress" style="flex:1">
      <div class="progress-bar"><div class="progress-fill" id="articleProgressFill" style="width:0%"></div></div>
      <span class="progress-time" id="articleProgressTime">0:00 / 5:00</span>
    </div>
    <span style="font-size:12px;color:var(--text-muted)">{listen_text}</span>
  </div>

  <!-- ARTICLE BODY -->
  <div class="article-body">

    {body_html}

    <div class="article-share">
      <p>{share_text}</p>
      <a href="../all-episodes.html" class="btn btn-primary">{more_text}</a>
    </div>
  </div>

  <!-- FOOTER -->
  <footer class="footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <a href="../" class="logo">
            <span class="logo-icon">&#9678;</span>
            <span class="logo-text">DeepCast<span class="logo-ai">AI</span></span>
          </a>
          <p class="footer-desc">{footer_desc}</p>
        </div>
        <div class="footer-links-group">
          <h4>{footer_svc}</h4>
          <ul>
            <li><a href="../#episodes">{footer_ep}</a></li>
            <li><a href="../#request">{footer_req}</a></li>
          </ul>
        </div>
        <div class="footer-links-group">
          <h4>{footer_legal}</h4>
          <ul>
            <li><a href="../terms.html">{"利用規約" if is_ja else "Terms of Service"}</a></li>
            <li><a href="../privacy.html">{"プライバシーポリシー" if is_ja else "Privacy Policy"}</a></li>
            <li><a href="../about.html">{"運営者情報" if is_ja else "About Us"}</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <p>&copy; 2026 DeepCast AI. All rights reserved.</p>
      </div>
    </div>
  </footer>

  <!-- MINI PLAYER -->
  <div class="mini-player" id="miniPlayer">
    <div class="mini-player-inner">
      <button class="mini-play-btn" id="miniPlayBtn" aria-label="{"再生/一時停止" if is_ja else "Play/Pause"}">
        <span class="play-icon">&#9654;</span>
      </button>
      <div class="mini-info">
        <span class="mini-title" id="miniTitle">-</span>
        <div class="mini-progress-wrap">
          <div class="mini-progress-bar" id="miniProgressBar">
            <div class="mini-progress-fill" id="miniProgressFill" style="width:0%"></div>
          </div>
          <span class="mini-time" id="miniTime">0:00 / 0:00</span>
        </div>
      </div>
      <button class="mini-close-btn" id="miniCloseBtn" aria-label="{"閉じる" if is_ja else "Close"}">&times;</button>
    </div>
  </div>

  <script src="../js/spa-router.js"></script>
</body>
</html>'''
    return html


def step2_publish():
    print("\n" + "="*60)
    print("STEP 2: PUBLISH EPISODES")
    print("="*60)

    new_json_entries = []

    for ep in EPISODE_PLAN:
        # Generate HTML
        html_content = generate_episode_html(ep)
        html_path = EPISODES_DIR / ep["html"]
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"  [OK] Created {html_path}")

        # Copy audio if source exists
        if ep["audio_src"]:
            src = AUDIO_SRC_DIR / ep["audio_src"]
            dst = EPISODES_DIR / ep["audio"]
            if src.exists():
                shutil.copy2(str(src), str(dst))
                print(f"  [OK] Copied audio {src.name} -> {ep['audio']}")
            else:
                print(f"  [WARN] Audio source not found: {src}")

        # Build JSON entry
        new_json_entries.append({
            "id": ep["ep_num"],
            "title": ep["title"],
            "description": ep["description"],
            "date": TODAY_DOT,
            "category": ep["category"].lower(),
            "tags": ep["tags"],
            "duration": "5:00",
            "audio": f"episodes/{ep['audio']}",
            "article": f"episodes/{ep['html']}",
        })

    # Update episodes.json - new at top, existing at bottom
    ej_path = EPISODES_DIR / "episodes.json"
    with open(ej_path, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # new entries in reverse order (8, 7, 6, 5, 4 -> newest first)
    new_json_entries.reverse()
    updated = new_json_entries + existing

    with open(ej_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
    print(f"  [OK] episodes.json updated: {len(updated)} entries total")

    # Update sitemap.xml
    sm_path = SITE_DIR / "sitemap.xml"
    with open(sm_path, "r", encoding="utf-8") as f:
        sitemap = f.read()

    new_sitemap_entries = ""
    for ep in EPISODE_PLAN:
        new_sitemap_entries += f"""
  <url>
    <loc>https://deepcast-ai.com/episodes/{ep["html"]}</loc>
    <lastmod>{TODAY}</lastmod>
    <changefreq>yearly</changefreq>
    <priority>0.7</priority>
  </url>"""

    sitemap = sitemap.replace("</urlset>", f"{new_sitemap_entries}\n</urlset>")
    with open(sm_path, "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"  [OK] sitemap.xml updated")

    # Update feed.xml
    feed_path = SITE_DIR / "feed.xml"
    with open(feed_path, "r", encoding="utf-8") as f:
        feed = f.read()

    pub_date = "Tue, 17 Mar 2026 12:00:00 +0900"
    new_feed_items = ""
    for ep in reversed(EPISODE_PLAN):  # newest first
        tags_str = ",".join(ep["tags"])
        new_feed_items += f"""
    <item>
      <title>#{ep["ep_num"]} {ep["title"]}</title>
      <description>{ep["description"]}</description>
      <enclosure url="https://deepcast-ai.com/episodes/{ep["audio"]}" type="audio/mpeg" length="0"/>
      <pubDate>{pub_date}</pubDate>
      <itunes:duration>5:00</itunes:duration>
      <itunes:episode>{ep["ep_num"]}</itunes:episode>
      <itunes:keywords>{tags_str}</itunes:keywords>
      <guid isPermaLink="false">deepcast-ep{ep["ep_num"]:03d}</guid>
    </item>
"""

    # Insert after the channel metadata, before the first existing <item>
    # Find the first <item> tag
    first_item_pos = feed.find("\n    <item>")
    if first_item_pos == -1:
        first_item_pos = feed.find("\n  </channel>")
    feed = feed[:first_item_pos] + new_feed_items + feed[first_item_pos:]

    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(feed)
    print(f"  [OK] feed.xml updated")

    # Update sw.js - increment cache version
    sw_path = SITE_DIR / "sw.js"
    with open(sw_path, "r", encoding="utf-8") as f:
        sw = f.read()
    sw = sw.replace("deepcast-v5", "deepcast-v6")
    with open(sw_path, "w", encoding="utf-8") as f:
        f.write(sw)
    print(f"  [OK] sw.js: CACHE_NAME -> deepcast-v6")


# ══════════════════════════════════════════
# STEP 3: GENERATE AUDIO
# ══════════════════════════════════════════
async def generate_audio_tts(text, voice, output_path):
    """Generate audio using edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def extract_text_from_html_body(html_body):
    """Strip HTML tags to get plain text for TTS."""
    text = re.sub(r'<[^>]+>', ' ', html_body)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def step3_generate_audio():
    print("\n" + "="*60)
    print("STEP 3: GENERATE AUDIO")
    print("="*60)

    for ep in EPISODE_PLAN:
        audio_path = EPISODES_DIR / ep["audio"]
        if audio_path.exists():
            size = audio_path.stat().st_size
            if size > 10000:  # > 10KB, seems valid
                print(f"  [SKIP] {ep['audio']} already exists ({size:,} bytes)")
                continue

        # Need to generate
        voice = "ja-JP-NanamiNeural" if ep["lang"] == "ja" else "en-US-GuyNeural"

        # Get text
        if ep["body"]:
            text = extract_text_from_html_body(ep["body"])
        elif ep["db_id"]:
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute("SELECT body FROM contents WHERE id = ?", (ep["db_id"],))
            row = c.fetchone()
            conn.close()
            text = row[0] if row else ""
        else:
            text = ep["description"]

        # Add intro/outro
        if ep["lang"] == "ja":
            intro = f"DeepCast AI、エピソード{ep['ep_num']}。{ep['title']}。"
            outro = "以上、DeepCast AIでした。ご視聴ありがとうございます。"
        else:
            intro = f"DeepCast AI, episode {ep['ep_num']}. {ep['title']}."
            outro = "That's all for this episode of DeepCast AI. Thank you for listening."

        full_text = f"{intro} {text} {outro}"

        # Truncate if too long (edge-tts can handle long text but let's be reasonable)
        if len(full_text) > 8000:
            full_text = full_text[:8000] + "... " + outro

        print(f"  [GEN] Generating {ep['audio']} ({voice}, {len(full_text)} chars)...")
        try:
            await generate_audio_tts(full_text, voice, audio_path)
            size = audio_path.stat().st_size
            print(f"  [OK] {ep['audio']} generated ({size:,} bytes)")
        except Exception as e:
            print(f"  [ERROR] Failed to generate {ep['audio']}: {e}")


# ══════════════════════════════════════════
# STEP 4: VERIFY
# ══════════════════════════════════════════
def step4_verify():
    print("\n" + "="*60)
    print("STEP 4: VERIFICATION")
    print("="*60)

    errors = []
    warnings = []

    # Check episodes.json
    ej_path = EPISODES_DIR / "episodes.json"
    with open(ej_path, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    ids_found = [e["id"] for e in episodes]
    expected_ids = [1, 2, 3, 4, 5, 6, 7, 8]
    for eid in expected_ids:
        if eid in ids_found:
            print(f"  [OK] episodes.json has id={eid}")
        else:
            errors.append(f"episodes.json missing id={eid}")
            print(f"  [ERROR] episodes.json missing id={eid}")

    # Check all HTML files exist
    for ep in episodes:
        html_path = SITE_DIR / ep["article"]
        if html_path.exists():
            print(f"  [OK] {ep['article']} exists")
        else:
            errors.append(f"Missing HTML: {ep['article']}")
            print(f"  [ERROR] Missing: {ep['article']}")

    # Check all audio files exist
    for ep in episodes:
        audio_path = SITE_DIR / ep["audio"]
        if audio_path.exists():
            size = audio_path.stat().st_size
            print(f"  [OK] {ep['audio']} exists ({size:,} bytes)")
        else:
            errors.append(f"Missing audio: {ep['audio']}")
            print(f"  [ERROR] Missing: {ep['audio']}")

    # Check sitemap.xml is valid
    sm_path = SITE_DIR / "sitemap.xml"
    with open(sm_path, "r", encoding="utf-8") as f:
        sitemap = f.read()
    if "ep004.html" in sitemap and "ep005.html" in sitemap and "ep008.html" in sitemap:
        print(f"  [OK] sitemap.xml contains new episodes")
    else:
        errors.append("sitemap.xml missing new episode entries")

    # Check no href="index.html" in new files
    for ep in EPISODE_PLAN:
        html_path = EPISODES_DIR / ep["html"]
        if html_path.exists():
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            if 'href="index.html"' in content or 'href="../index.html"' in content:
                errors.append(f"{ep['html']} contains href to index.html")
                print(f"  [ERROR] {ep['html']} has href to index.html")
            else:
                print(f"  [OK] {ep['html']} no index.html links")

    # Check sw.js version
    sw_path = SITE_DIR / "sw.js"
    with open(sw_path, "r", encoding="utf-8") as f:
        sw = f.read()
    if "deepcast-v6" in sw:
        print(f"  [OK] sw.js CACHE_NAME = deepcast-v6")
    else:
        errors.append("sw.js not updated to v6")

    # Check feed.xml
    feed_path = SITE_DIR / "feed.xml"
    with open(feed_path, "r", encoding="utf-8") as f:
        feed = f.read()
    # Should NOT have the old test ep004 entry
    if "The Role of Emotional Intelligence in Leadership" in feed:
        errors.append("feed.xml still has old test ep004 entry")
        print(f"  [ERROR] feed.xml still has old test ep004 entry")
    else:
        print(f"  [OK] feed.xml cleaned of old test entries")

    # Summary
    print("\n" + "-"*40)
    if errors:
        print(f"RESULT: {len(errors)} ERRORS found:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("RESULT: ALL CHECKS PASSED!")
    print("-"*40)


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
async def main():
    print("DeepCast Production Cleanup & Publish")
    print(f"Date: {TODAY}")
    print(f"Engine: {ENGINE_DIR}")
    print(f"Site: {SITE_DIR}")

    step1_cleanup()
    step2_publish()
    await step3_generate_audio()
    step4_verify()

    print("\n\nDONE!")

if __name__ == "__main__":
    asyncio.run(main())
