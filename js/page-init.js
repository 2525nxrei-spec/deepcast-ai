// ===================================================================
//  DeepCast AI - Page Initializers
//  エピソード表示、フィルター、カテゴリ検出、構造化データ、
//  各ページ固有のUI初期化（FAQ、モーダル、フォーム等）
// ===================================================================

(function () {
  'use strict';

  // DeepCastAudioへの参照（audio-player.jsで定義済み）
  var DA = window.DeepCastAudio;

  // ===== 言語切替 =====
  window.deepcastLang = localStorage.getItem('deepcastLang') || 'ja';

  function filterByLang(episodes) {
    return episodes.filter(function(ep) {
      return !ep.language || ep.language === window.deepcastLang;
    });
  }

  function initLangSwitch() {
    document.querySelectorAll('.lang-switch').forEach(function(sw) {
      sw.querySelectorAll('.lang-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.lang === window.deepcastLang);
        btn.addEventListener('click', function() {
          if (btn.dataset.lang === window.deepcastLang) return;
          window.deepcastLang = btn.dataset.lang;
          localStorage.setItem('deepcastLang', window.deepcastLang);
          document.querySelectorAll('.lang-btn').forEach(function(b) {
            b.classList.toggle('active', b.dataset.lang === window.deepcastLang);
          });
          initIndexEpisodes();
          initAllEpisodesPage();
        });
      });
    });
  }

  // =========================================================
  //  カテゴリ自動検出（タイトル・説明・タグからスコアリング）
  // =========================================================
  var CATEGORY_KEYWORDS = {
    tech: [
      '機械学習', 'ディープラーニング', '深層学習',
      'プログラミング', 'ブロックチェーン', 'Web3', '半導体', 'チップ',
      '量子コンピュータ', 'サイバー', 'ハッキング', 'プラットフォーム', 'クラウド',
      'ロボット', '自動運転', 'VR', 'AR', 'メタバース', '5G', '6G', 'IoT',
      'スマートフォン', 'アプリ', 'ソフトウェア', 'ハードウェア', 'API',
      'オープンソース', 'テクノロジー', 'デジタル', 'ネットワーク',
      '暗号化', 'セキュリティ', 'データセンター', 'サーバー', '通信',
      'Google', 'OpenAI', 'Apple', 'Microsoft', 'NVIDIA',
      'GAFAM', '海底ケーブル', 'TSMC', 'サプライチェーン',
      'コンピュータ', 'GPU', 'CPU', 'クラウドコンピューティング'
    ],
    business: [
      '経済学', 'ビジネス', '投資', '株', '資産', '金融', '起業', 'スタートアップ',
      'マーケティング', '経営', '利益', '市場', 'GDP', 'インフレ', 'デフレ',
      '円安', '円高', '為替', '貿易', 'サブスク', '年収', '所得', '給料',
      '不動産', 'ローン', '保険', '年金', '税金', '節税', '副業', '転職',
      'リモートワーク', 'フリーランス', 'キャリア', '貯金', '貯蓄',
      '消費', '購買', 'マネー', 'ファイナンス', '資本主義',
      'ベーシックインカム', 'ビットコイン', '暗号資産',
      '宝くじ', 'MMT', '通貨', '貨幣', '推し活', 'DAO',
      '老後', '2000万', '貧困', '富裕層', '所得格差',
      '技術的失業', '雇用', 'VC', '資金調達'
    ],
    science: [
      '科学', 'サイエンス', '物理', '化学', '生物学', '数学', '医学', '医療',
      '遺伝子', 'DNA', 'ゲノム', '宇宙', '天文', '量子', '素粒子',
      '相対性理論', '脳', '神経', 'ニューロン', '認知科学',
      '論文', '臨床', '細胞', 'ウイルス', '免疫',
      'バイオテクノロジー', 'エネルギー', '核融合', '気候変動',
      '生態系', '絶滅', '火星', 'ブラックホール', '暗黒物質', 'フェルミ',
      '脳科学', '神経美学', 'ドーパミン', 'セロトニン',
      '睡眠', '記憶', '知能', 'IQ', '老化', 'テロメア', 'CRISPR',
      '哲学ゾンビ', '多世界解釈', '進化論', '実験心理学',
      '発達心理学', '神経科学', '認知バイアス'
    ],
    society: [
      '社会', '文化', '政治', '法律', '倫理', '道徳', '哲学', '宗教',
      '歴史', '戦争', '平和', '民主主義', '独裁', '権力', '差別',
      '人権', '自由', 'ジェンダー', '教育', '学校', '子ども', '少子化',
      '高齢化', '人口', '移民', 'メディア', 'SNS', 'フェイクニュース',
      '陰謀論', '選挙', '世論', 'プロパガンダ', '心理操作',
      '犯罪', '刑法', '裁判', '司法', '冤罪', '監視社会', '死刑',
      '恋愛', '結婚', '家族', 'コミュニティ', '孤独', '幸福',
      'ディストピア', 'ユートピア', 'シンギュラリティ', '存在',
      'アイデンティティ', '正義', '功利主義',
      '監視', '国家', '統治', '労働', '格差', '中間層', '失業',
      '生存戦略', '人間関係', '対人', '葛藤', 'バイアス',
      '地政学', 'AI倫理'
    ]
  };

  var CATEGORY_LABELS = {
    tech: 'テクノロジー',
    business: 'ビジネス',
    science: 'サイエンス',
    society: '社会・文化'
  };

  function autoDetectCategory(ep) {
    var title = (ep.title || '').toLowerCase();
    var desc = (ep.description || '').toLowerCase();
    var tagsText = (ep.tags || []).join(' ').toLowerCase();
    var scores = { tech: 0, business: 0, science: 0, society: 0 };

    for (var cat in CATEGORY_KEYWORDS) {
      CATEGORY_KEYWORDS[cat].forEach(function(kw) {
        var kwLower = kw.toLowerCase();
        if (title.indexOf(kwLower) !== -1) scores[cat] += 2;
        if (desc.indexOf(kwLower) !== -1) scores[cat] += 1;
        if (tagsText.indexOf(kwLower) !== -1) scores[cat] += 3;
      });
    }

    var best = 'society';
    var bestScore = 0;
    for (var c in scores) {
      if (scores[c] > bestScore) { bestScore = scores[c]; best = c; }
    }
    return best;
  }

  function autoAssignCategories(episodes) {
    episodes.forEach(function(ep) { ep.category = autoDetectCategory(ep); });
    return episodes;
  }

  // オーディオファイル名 → 記事URLマッピングを構築
  // 音声URLを生成
  // audioIdがある場合はAPI経由（認証付き、Proアクセス制御あり）
  // audioIdがない場合: proエピソードならaudioフィールドからIDを抽出してAPI経由に、freeならaudioフィールド直接参照
  function resolveAudioUrl(ep) {
    if (ep.audioId) return '/api/audio/' + ep.audioId;
    // audioIdがないproエピソード: audioフィールドからep0XXパターンを抽出
    if (ep.tier === 'pro' && ep.audio) {
      var match = ep.audio.match(/ep(\d{3})/);
      if (match) return '/api/audio/ep' + match[1];
    }
    return ep.audio || '';
  }

  function buildArticleMap(episodes) {
    var audioToArticle = DA.audioToArticle;
    episodes.forEach(function(ep) {
      var audioUrl = resolveAudioUrl(ep);
      if (audioUrl && ep.article) {
        audioToArticle[DA.audioFileName(audioUrl)] = ep.article;
      }
    });
  }

  // フィルターボタンを動的生成
  function buildFilterButtons(container, episodes) {
    var cats = {};
    episodes.forEach(function(ep) { if (ep.category) cats[ep.category] = true; });
    var html = '<button class="filter-btn active" data-filter="all">すべて</button>';
    ['tech', 'business', 'science', 'society'].forEach(function(cat) {
      if (cats[cat]) {
        html += '<button class="filter-btn" data-filter="' + cat + '">' + (CATEGORY_LABELS[cat] || cat) + '</button>';
      }
    });
    container.innerHTML = html;
  }

  // 統計カウンターアニメーション
  function animateCounter(el) {
    var target = parseInt(el.dataset.count);
    if (!target || target <= 0) return;
    var start = performance.now();
    var tick = function(now) {
      var p = Math.min((now - start) / 500, 1);
      el.textContent = Math.floor((1 - Math.pow(1 - p, 3)) * target).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // エピソードカードのHTML生成
  // episodeIndex: episodes配列内のインデックス（0が最新）
  function renderEpisode(ep, episodeIndex) {
    var tags = ep.tags.map(function(t) { return '<span class="tag">' + t + '</span>'; }).join('');
    // タイトルのエスケープ（aria-label用）
    var safeTitle = (ep.title || '').replace(/"/g, '&quot;');

    // Pro判定: DEEPCAST_AUTHが読み込まれていればisPro()を使い、なければfalse
    var userIsPro = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.isPro());
    // episodes.jsonのtierフィールドに基づいてロック判定（tier === 'pro' かつユーザーがPro未加入ならロック）
    var isLocked = !userIsPro && ep.tier === 'pro';
    var lockedClass = isLocked ? ' locked' : '';
    var lockedAttr = isLocked ? ' data-locked="true"' : '';
    var proBadge = isLocked ? '<span class="episode-badge pro-badge">Pro</span>' : '';

    // ロックアイコン（再生ボタン上に重ねる）
    var lockIconHtml = isLocked
      ? '<span class="lock-icon"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>'
      : '';

    return '<article class="episode-card' + lockedClass + '" data-category="' + ep.category + '" aria-label="エピソード: ' + safeTitle + '">' +
      '<div class="episode-header">' +
        '<div class="episode-info">' +
          '<span class="episode-badge category-' + ep.category + '">' + (CATEGORY_LABELS[ep.category] || '') + '</span>' +
          proBadge +
          '<span class="episode-number">#' + ep.id + '</span>' +
          '<span class="episode-date">' + ep.date + '</span>' +
          '<span class="episode-duration" aria-label="再生時間 ' + ep.duration + '">' + ep.duration + '</span>' +
        '</div>' +
        '<h3 class="episode-title">' + ep.title + '</h3>' +
        '<p class="episode-desc">' + ep.description + '</p>' +
        '<div class="episode-tags" role="list" aria-label="タグ">' + tags + '</div>' +
      '</div>' +
      '<div class="episode-embed">' +
        '<div class="episode-player" role="group" aria-label="オーディオプレイヤー: ' + safeTitle + '">' +
          '<button class="play-btn" data-audio="' + resolveAudioUrl(ep) + '" data-title="' + safeTitle + '"' + lockedAttr + ' role="button" aria-label="' + (isLocked ? 'Proプラン限定: ' : '再生: ') + safeTitle + '" tabindex="0">' +
            '<span class="play-icon">&#9654;</span>' +
            lockIconHtml +
          '</button>' +
          '<div class="episode-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="再生進捗">' +
            '<div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div>' +
            '<span class="progress-time" aria-live="off">0:00 / ' + ep.duration + '</span>' +
          '</div>' +
        '</div>' +
        (ep.article ? '<a href="' + ep.article + '" class="read-article-btn" aria-label="' + safeTitle + ' の要約を読む">要約を読む &rarr;</a>' : '') +
      '</div>' +
    '</article>';
  }

  // =========================================================
  //  ページ固有の初期化関数群
  // =========================================================

  function initFloatingFormulas() {
    var container = document.querySelector('.hero-formulas');
    if (!container) return;
    var items = container.querySelectorAll('.formula');
    var w = window.innerWidth;
    var scale = Math.min(Math.max(w / 1200, 0.45), 1);
    var minSize = Math.round(16 * scale);
    var maxSize = Math.round(26 * scale);
    var state = [];
    items.forEach(function(el) {
      var size = minSize + Math.random() * (maxSize - minSize);
      var x = 5 + Math.random() * 90;
      var y = 5 + Math.random() * 90;
      var rot = -15 + Math.random() * 30;
      var vx = (0.3 + Math.random() * 0.7) * (Math.random() < 0.5 ? 1 : -1);
      var vy = (0.2 + Math.random() * 0.5) * (Math.random() < 0.5 ? 1 : -1);
      el.style.left = x + '%';
      el.style.top = y + '%';
      el.style.fontSize = Math.round(size) + 'px';
      el.style.transform = 'rotate(' + rot.toFixed(1) + 'deg)';
      el.style.opacity = '1';
      state.push({ el: el, x: x, y: y, vx: vx, vy: vy, rot: rot });
    });
    if (window._formulaAnimId) cancelAnimationFrame(window._formulaAnimId);
    var last = performance.now();
    function tick(now) {
      var dt = (now - last) / 1000;
      last = now;
      for (var i = 0; i < state.length; i++) {
        var s = state[i];
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        if (s.x < 2) { s.x = 2; s.vx = Math.abs(s.vx); }
        if (s.x > 95) { s.x = 95; s.vx = -Math.abs(s.vx); }
        if (s.y < 2) { s.y = 2; s.vy = Math.abs(s.vy); }
        if (s.y > 95) { s.y = 95; s.vy = -Math.abs(s.vy); }
        s.el.style.left = s.x + '%';
        s.el.style.top = s.y + '%';
      }
      window._formulaAnimId = requestAnimationFrame(tick);
    }
    window._formulaAnimId = requestAnimationFrame(tick);
  }

  function initReveal() {
    var els = document.querySelectorAll(
      '.episode-card,.service-card,.step-card,.pricing-card,.testimonial-card,.faq-item,.request-form-card,.request-info-card'
    );
    if (!els.length) return;
    var obs = new IntersectionObserver(function(entries) {
      entries.forEach(function(en) {
        if (en.isIntersecting) {
          en.target.style.opacity = '1';
          en.target.style.transform = 'translateY(0)';
          obs.unobserve(en.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });
    els.forEach(function(el, i) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(12px)';
      el.style.transition = 'opacity 0.4s ease ' + ((i % 3) * 0.06) + 's, transform 0.4s ease ' + ((i % 3) * 0.06) + 's';
      obs.observe(el);
    });
  }

  function initModal() {
    var modal = document.getElementById('signupModal');
    if (!modal) return;
    var modalTitle = document.getElementById('modalTitle');
    var modalDesc = document.getElementById('modalDesc');
    var modalClose = document.getElementById('modalClose');
    var currentPlan = null;

    function openModal(title, desc) {
      if (modalTitle) modalTitle.textContent = title || '無料で始める';
      if (modalDesc) modalDesc.textContent = desc || 'メールアドレスで簡単登録';
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
    function closeModal() {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
    if (modalClose) modalClose.addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });

    document.querySelectorAll('[data-action]').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var msgs = {
          'signup-free': ['無料で始める', 'メールアドレスで簡単登録。', 'free'],
          'contact': ['お問い合わせ', 'ご質問・ご相談はこちらから。', null]
        };
        var m = msgs[btn.dataset.action];
        if (m) { currentPlan = m[2]; openModal(m[0], m[1]); }
      });
    });

    var signupForm = document.getElementById('signupForm');
    if (signupForm) {
      signupForm.addEventListener('submit', function(e) {
        e.preventDefault();
        var btn = e.target.querySelector('button[type="submit"]');
        // 二重クリック防止
        if (btn.disabled) return;
        var emailVal = document.getElementById('email').value;
        btn.classList.add('btn-loading');
        btn.disabled = true;
        var planName = currentPlan || 'free';
        fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ email: emailVal, plan: planName, _subject: 'DeepCast AI 新規会員登録 (' + planName + ')', _captcha: 'false' })
        })
        .then(function(r) { return r.json(); })
        .then(function() {
          localStorage.setItem('deepcast_member', JSON.stringify({ email: emailVal, plan: planName, registered: new Date().toISOString() }));
          e.target.innerHTML = '<div style="text-align:center;padding:24px 0"><div style="font-size:24px;margin-bottom:8px">&#10003;</div><h3 style="font-size:17px;font-weight:600;margin-bottom:4px">登録完了</h3><p style="color:var(--text-secondary);font-size:13px">' + emailVal + ' で登録しました。</p></div>';
          setTimeout(closeModal, 3000);
        })
        .catch(function() {
          btn.classList.remove('btn-loading');
          btn.textContent = 'ネットワークエラー。接続を確認してください。';
          setTimeout(function() { btn.textContent = '無料で登録する'; btn.disabled = false; }, 3000);
        });
      });
    }
  }

  function initRequestForm() {
    var reqForm = document.getElementById('requestForm');
    if (!reqForm) return;
    reqForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var btn = reqForm.querySelector('button[type="submit"]');
      // 二重クリック防止
      if (btn.disabled) return;
      var data = new FormData(reqForm);
      var body = {
        topic: data.get('topic'), category: data.get('category'), depth: data.get('depth'),
        detail: data.get('detail'), email: data.get('email'),
        _subject: 'DeepCast AI 新規リクエスト', _captcha: 'false'
      };
      var origText = btn.textContent;
      btn.classList.add('btn-loading');
      btn.disabled = true;
      fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      })
      .then(function(r) { return r.json(); })
      .then(function() {
        btn.classList.remove('btn-loading');
        btn.textContent = '受付完了!';
        btn.style.background = '#3a8a44';
        setTimeout(function() { reqForm.reset(); btn.textContent = origText; btn.style.background = ''; btn.disabled = false; }, 3000);
      })
      .catch(function() {
        btn.classList.remove('btn-loading');
        btn.textContent = 'ネットワークエラー。接続を確認してください。';
        setTimeout(function() { btn.textContent = origText; btn.disabled = false; }, 3000);
      });
    });
  }

  function initPopularTags() {
    document.querySelectorAll('.popular-tag').forEach(function(tag) {
      tag.addEventListener('click', function() {
        var f = document.getElementById('requestTopic');
        if (f) { f.value = tag.dataset.topic; f.focus(); f.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    });
  }

  function initIndexEpisodes() {
    var episodeList = document.getElementById('episodeList');
    if (!episodeList) return;
    // all-episodesページには検索バーがあるので除外
    if (document.getElementById('episodeSearch')) return;

    fetch('/episodes/episodes.json')
      .then(function(r) { return r.json(); })
      .then(function(allEps) {
        autoAssignCategories(allEps);
        buildArticleMap(allEps);
        var episodes = filterByLang(allEps);
        if (!episodes.length) {
          episodeList.innerHTML = '<p class="loading-text">新しいエピソードを準備中です。もうしばらくお待ちください。</p>';
          return;
        }
        var filterContainer = document.querySelector('.episode-filters');
        if (filterContainer) buildFilterButtons(filterContainer, episodes);

        episodeList.innerHTML = episodes.map(function(ep, idx) { return renderEpisode(ep, idx); }).join('');
        document.querySelectorAll('.stat-number[data-count]').forEach(function(el) {
          el.dataset.count = episodes.length;
          animateCounter(el);
        });
        episodeList.querySelectorAll('.play-btn').forEach(function(btn) {
          if (btn.dataset.locked === 'true') {
            btn.addEventListener('click', function(e) {
              e.preventDefault();
              e.stopPropagation();
              if (typeof DEEPCAST_AUTH !== 'undefined') {
                DEEPCAST_AUTH.showUpgradeGate();
              }
            });
          } else {
            DA.bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
          }
        });
        var btns = document.querySelectorAll('.filter-btn');
        var cards = document.querySelectorAll('.episode-card');
        btns.forEach(function(btn) {
          btn.addEventListener('click', function() {
            btns.forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            cards.forEach(function(c) {
              c.style.display = (btn.dataset.filter === 'all' || c.dataset.category === btn.dataset.filter) ? '' : 'none';
            });
            DA.buildPlaylist();
          });
        });
        DA.buildPlaylist();
        initReveal();
        DA.reassociatePlayingButton();
      })
      .catch(function() {
        var fallback = [
          { id: 3, title: "GPT-5 vs Gemini 2.5：次世代AIの覇権争い", description: "OpenAIとGoogleの最新モデル比較。", date: "2026.03.02", category: "tech", tags: ["AI", "テクノロジー"], duration: "5:12", tier: "free", audio: "" },
          { id: 2, title: "スタートアップ資金調達の新常識 2026", description: "VC市場の変化、AIスタートアップへの投資トレンド。", date: "2026.03.01", category: "business", tags: ["ビジネス"], duration: "4:58", tier: "free", audio: "" },
          { id: 1, title: "量子コンピュータの実用化が見えてきた", description: "IBMとGoogleの量子超越性競争。実用化のユースケース。", date: "2026.02.28", category: "science", tags: ["サイエンス"], duration: "5:31", tier: "pro", audio: "" }
        ];
        episodeList.innerHTML = fallback.map(function(ep, idx) { return renderEpisode(ep, idx); }).join('');
        episodeList.querySelectorAll('.play-btn').forEach(function(btn) {
          if (btn.dataset.locked === 'true') {
            btn.addEventListener('click', function(e) {
              e.preventDefault();
              e.stopPropagation();
              if (typeof DEEPCAST_AUTH !== 'undefined') {
                DEEPCAST_AUTH.showUpgradeGate();
              }
            });
          } else {
            DA.bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
          }
        });
        DA.buildPlaylist();
        initReveal();
      });
  }

  function initAllEpisodesPage() {
    var episodeSearch = document.getElementById('episodeSearch');
    if (!episodeSearch) return;
    var episodeList = document.getElementById('episodeList');
    var episodeCount = document.getElementById('episodeCount');
    var noResults = document.getElementById('noResults');
    if (!episodeList) return;

    var allEpisodes = [];
    var activeFilter = 'all';

    function displayEpisodes(episodes) {
      if (!episodes.length) {
        episodeList.innerHTML = '';
        if (noResults) noResults.style.display = 'block';
        if (episodeCount) episodeCount.textContent = '';
        return;
      }
      if (noResults) noResults.style.display = 'none';
      episodeList.innerHTML = episodes.map(function(ep) { return renderEpisode(ep, ep._originalIndex); }).join('');
      if (episodeCount) episodeCount.textContent = episodes.length + '件のエピソード';
      episodeList.querySelectorAll('.play-btn').forEach(function(btn) {
        if (btn.dataset.locked === 'true') {
          btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof DEEPCAST_AUTH !== 'undefined') {
              DEEPCAST_AUTH.showUpgradeGate();
            }
          });
        } else {
          DA.bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
        }
      });
      DA.buildPlaylist();
      DA.reassociatePlayingButton();
    }

    function applyFilters() {
      var query = episodeSearch.value.toLowerCase();
      var filtered = allEpisodes.filter(function(ep) {
        var matchCategory = activeFilter === 'all' || ep.category === activeFilter;
        var matchSearch = !query ||
          ep.title.toLowerCase().includes(query) ||
          ep.description.toLowerCase().includes(query) ||
          ep.tags.some(function(t) { return t.toLowerCase().includes(query); });
        return matchCategory && matchSearch;
      });
      displayEpisodes(filtered);
    }

    fetch('/episodes/episodes.json')
      .then(function(r) { return r.json(); })
      .then(function(rawEpisodes) {
        autoAssignCategories(rawEpisodes);
        buildArticleMap(rawEpisodes);
        var episodes = filterByLang(rawEpisodes);
        // 各エピソードに元のインデックスを付与（Free/Pro判定用）
        episodes.forEach(function(ep, idx) { ep._originalIndex = idx; });
        var filterContainer = document.querySelector('.episode-filters');
        if (filterContainer) {
          buildFilterButtons(filterContainer, episodes);
          var filterBtns2 = filterContainer.querySelectorAll('.filter-btn');
          filterBtns2.forEach(function(btn) {
            btn.addEventListener('click', function() {
              filterBtns2.forEach(function(b) { b.classList.remove('active'); });
              btn.classList.add('active');
              activeFilter = btn.dataset.filter;
              applyFilters();
            });
          });
        }
        allEpisodes = episodes;
        displayEpisodes(episodes);
      })
      .catch(function() {
        episodeList.innerHTML = '<p class="loading-text">エピソードの読み込みに失敗しました。インターネット接続を確認の上、ページを再読み込みしてください。</p>';
      });

    episodeSearch.addEventListener('input', applyFilters);
  }

  // 記事ページの動的プレイヤー構築（audioタグ削除対応）
  function initArticleDynamicPlayer() {
    var container = document.getElementById('articleAudioPlayer');
    if (!container) return;
    var episodeId = container.dataset.episode;
    if (!episodeId) return;
    var audioSrc = '/api/audio/' + episodeId;
    // 記事タイトルを取得
    var titleEl = document.querySelector('.article-title');
    var title = titleEl ? titleEl.textContent : episodeId;

    // プレイヤーUIを構築
    container.innerHTML =
      '<div class="episode-player" role="group" aria-label="オーディオプレイヤー">' +
        '<button class="play-btn" id="articlePlayBtn" data-audio="' + audioSrc + '" data-title="' + title.replace(/"/g, '&quot;') + '" role="button" aria-label="再生: ' + title.replace(/"/g, '&quot;') + '" tabindex="0">' +
          '<span class="play-icon">&#9654;</span>' +
        '</button>' +
        '<div class="episode-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">' +
          '<div class="progress-bar"><div class="progress-fill" id="articleProgressFill" style="width:0%"></div></div>' +
          '<span class="progress-time" id="articleProgressTime">0:00</span>' +
        '</div>' +
      '</div>';
  }

  function initArticlePlayer() {
    // まず動的プレイヤーを構築
    initArticleDynamicPlayer();
    var btn = document.getElementById('articlePlayBtn');
    if (!btn) return;
    // ロック済みの場合はbindしない（ゲーティングスクリプトが処理済み）
    if (btn.dataset.locked === 'true') return;
    var audioSrc = btn.dataset.audio;
    var title = btn.dataset.title;
    if (!audioSrc) return;

    var userIsPro = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.isPro());

    // body data-tier="pro" による判定（静的HTMLに埋め込み済み）
    var pageTier = document.body.dataset.tier || 'free';
    if (!userIsPro && pageTier === 'pro') {
      // Proページかつ非Proユーザー → ロック
      btn.dataset.locked = 'true';
      btn.innerHTML = '<span class="play-icon">&#9654;</span><span class="lock-icon"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>';
      btn.addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation();
        if (typeof DEEPCAST_AUTH !== 'undefined') DEEPCAST_AUTH.showUpgradeGate();
      });
      return;
    }

    if (!userIsPro) {
      // episodes.jsonでもインデックスベースの判定（フォールバック）
      fetch('/episodes/episodes.json')
        .then(function(r) { return r.json(); })
        .then(function(episodes) {
          if (!episodes || !episodes.length) {
            // episodes.jsonが空の場合、pageTierで判定済みなのでbindしてOK
            DA.bindPlayer(btn, audioSrc, title);
            return;
          }
          var audioIdFromSrc = audioSrc.split('/').pop().split('?')[0];
          var idx = -1;
          for (var i = 0; i < episodes.length; i++) {
            var epAudioId = (episodes[i].audioId || '');
            if (epAudioId === audioIdFromSrc) { idx = i; break; }
          }
          // tierフィールドでもチェック（episodes.jsonにtier: 'pro'があればロック）
          var epTier = (idx >= 0 && episodes[idx].tier) ? episodes[idx].tier : 'free';
          if (epTier === 'pro' || idx >= 3) {
            btn.dataset.locked = 'true';
            btn.innerHTML = '<span class="play-icon">&#9654;</span><span class="lock-icon"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>';
            btn.addEventListener('click', function(e) {
              e.preventDefault(); e.stopPropagation();
              if (typeof DEEPCAST_AUTH !== 'undefined') DEEPCAST_AUTH.showUpgradeGate();
            });
          } else {
            DA.bindPlayer(btn, audioSrc, title);
          }
        })
        .catch(function() {
          // episodes.json取得失敗時はpageTierで判定済みなのでbind
          DA.bindPlayer(btn, audioSrc, title);
        });
    } else {
      DA.bindPlayer(btn, audioSrc, title);
    }
  }

  function initContactForm() {
    var form = document.querySelector('.contact-form');
    if (!form) return;
    if (form.getAttribute('action') && form.getAttribute('method') === 'POST') {
      form.addEventListener('submit', function(e) {
        e.preventDefault();
        var btn = form.querySelector('.form-submit') || form.querySelector('button[type="submit"]');
        // 二重クリック防止
        if (btn && btn.disabled) return;
        var data = new FormData(form);
        var origText = btn ? btn.textContent : '';
        if (btn) { btn.classList.add('btn-loading'); btn.disabled = true; }

        fetch(form.action, {
          method: 'POST',
          body: data,
          headers: { 'Accept': 'application/json' }
        })
        .then(function(r) {
          if (r.ok) {
            form.innerHTML = '<div style="text-align:center;padding:48px 0"><div style="font-size:32px;margin-bottom:12px">&#10003;</div><h3 style="font-size:18px;font-weight:600;margin-bottom:8px">送信完了</h3><p style="color:var(--text-secondary);font-size:14px">お問い合わせありがとうございます。<br>通常2営業日以内にご返信いたします。</p></div>';
          } else {
            throw new Error('Failed');
          }
        })
        .catch(function() {
          if (btn) {
            btn.classList.remove('btn-loading');
            btn.textContent = 'ネットワークエラー。接続を確認してください。';
            setTimeout(function() { btn.textContent = origText; btn.disabled = false; }, 3000);
          }
        });
      });
    }
  }

  // =========================================================
  //  reinitPage — SPA遷移後に全ページ機能を再初期化
  // =========================================================
  // ハンバーガーメニューのイベント委譲（nav要素に1度だけ設定）
  var navDelegated = false;

  function reinitPage() {
    // ハンバーガーメニュー（イベント委譲方式でリスナー蓄積を防止）
    var navbar = document.getElementById('navbar');
    var navLinks = document.getElementById('navLinks');
    if (navbar && navLinks && !navDelegated) {
      var navActions = navbar.querySelector('.nav-actions');
      navbar.addEventListener('click', function(e) {
        // ハンバーガーボタンのクリック
        if (e.target.closest('#hamburger')) {
          navLinks.classList.toggle('active');
          // モバイルメニュー展開時にログインボタン等も表示
          if (navActions) navActions.classList.toggle('active');
          return;
        }
        // ナビリンクのクリックでメニューを閉じる
        if (e.target.closest('#navLinks a') || e.target.closest('.nav-actions a')) {
          navLinks.classList.remove('active');
          if (navActions) navActions.classList.remove('active');
        }
      });
      navDelegated = true;
    }

    // ミニプレイヤー
    DA.bindMiniPlayer();

    // スムーズスクロール（ハッシュリンク）
    document.querySelectorAll('a[href^="#"]').forEach(function(a) {
      a.addEventListener('click', function(e) {
        var href = this.getAttribute('href');
        if (href === '#' || href === '') return;
        var t = document.querySelector(href);
        if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth' }); }
      });
    });

    // FAQ（アクセシビリティ対応: aria-expanded切り替え）
    document.querySelectorAll('.faq-item').forEach(function(item) {
      var q = item.querySelector('.faq-question');
      if (q) {
        q.addEventListener('click', function() {
          var wasActive = item.classList.contains('active');
          document.querySelectorAll('.faq-item').forEach(function(i) {
            i.classList.remove('active');
            var btn = i.querySelector('.faq-question');
            if (btn) btn.setAttribute('aria-expanded', 'false');
          });
          if (!wasActive) {
            item.classList.add('active');
            q.setAttribute('aria-expanded', 'true');
          }
        });
        // キーボード操作: スペース/Enterで開閉
        q.addEventListener('keydown', function(e) {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault();
            q.click();
          }
        });
      }
    });

    // SNS Coming Soon
    document.querySelectorAll('.sns-coming-soon').forEach(function(a) {
      a.addEventListener('click', function(e) {
        e.preventDefault();
        var toast = document.createElement('div');
        toast.textContent = 'SNSアカウントは準備中です';
        toast.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:12px 24px;border-radius:8px;font-size:14px;z-index:9999;opacity:0;transition:opacity .3s';
        document.body.appendChild(toast);
        requestAnimationFrame(function() { toast.style.opacity = '1'; });
        setTimeout(function() { toast.style.opacity = '0'; setTimeout(function() { toast.remove(); }, 300); }, 2500);
      });
    });

    // 浮遊数式アニメーション（indexページ）
    initFloatingFormulas();

    // ナビバーのスクロール挙動
    var navbar = document.getElementById('navbar');
    if (navbar) {
      var isIndex = (function() { var p = location.pathname.replace(/\/index\.html$/, '/'); return p.endsWith('/') || p === ''; })();
      if (!isIndex) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.toggle('scrolled', window.scrollY > 20);
      }
    }

    // リビールアニメーション
    initReveal();

    // モーダル
    initModal();

    // リクエストフォーム
    initRequestForm();

    // 人気タグ
    initPopularTags();

    // 言語切替
    initLangSwitch();

    // エピソード読み込み（indexページ）
    initIndexEpisodes();

    // 全エピソードページ
    initAllEpisodesPage();

    // お問い合わせフォーム
    initContactForm();

    // 記事ページプレイヤー
    initArticlePlayer();

    // 再生中ボタンの再関連付け
    DA.reassociatePlayingButton();

    // トップへスクロール（ハッシュがなければ）
    if (!location.hash) {
      window.scrollTo(0, 0);
    } else {
      var target = document.querySelector(location.hash);
      if (target) {
        setTimeout(function() { target.scrollIntoView({ behavior: 'smooth' }); }, 100);
      }
    }
  }

  // グローバルに公開（spa-router.jsから呼ばれる）
  window.DeepCastPage = {
    reinitPage: reinitPage
  };

})();
