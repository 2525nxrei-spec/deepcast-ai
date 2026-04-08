// ===================================================================
//  DeepCast AI - Pro記事ゲーティング
//  Proエピソードの本文を非Pro/未ログインユーザーから隠す
//  data-tier="pro" が付いたページで動作
// ===================================================================

(function () {
  'use strict';

  // ページのティア属性を取得（HTMLの<body data-tier="pro">で指定）
  function getPageTier() {
    return document.body.dataset.tier || 'free';
  }

  // Pro記事のゲーティングを適用
  function applyProGate() {
    if (getPageTier() !== 'pro') return;

    // auth.jsの初期化を待ってから判定
    var checkAccess = function () {
      var userIsPro = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.isPro());
      if (userIsPro) return; // Proユーザーはそのまま

      // --- 本文を隠す ---
      var articleBody = document.querySelector('.article-body');
      var articleDeep = document.querySelector('.article-deep');

      if (articleBody) {
        // 最初のh2+pだけ残して残りを隠す
        var children = Array.from(articleBody.children);
        var showCount = 0; // 最初のh2とその直後のp（2要素）だけ見せる
        var gateInserted = false;
        children.forEach(function (child) {
          if (showCount < 2) {
            showCount++;
          } else {
            child.style.display = 'none';
            child.setAttribute('data-pro-hidden', 'true');
          }
        });

        // グラデーションフェードアウト+ゲートUIを挿入
        if (!document.getElementById('proArticleGate')) {
          var gate = document.createElement('div');
          gate.id = 'proArticleGate';
          gate.innerHTML =
            '<div style="position:relative;margin-top:-40px;padding-top:60px;' +
            'background:linear-gradient(to bottom,transparent,var(--bg,#fff) 70%);text-align:center;padding-bottom:40px">' +
            '<div style="width:48px;height:48px;border-radius:8px;background:#e8e0f0;' +
            'display:flex;align-items:center;justify-content:center;margin:0 auto 16px">' +
            '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b21a8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>' +
            '</div>' +
            '<h3 style="font-size:1.1rem;font-weight:700;margin-bottom:8px;color:var(--text,#1d1d1f)">この先はProプラン限定です</h3>' +
            '<p style="font-size:0.88rem;color:var(--text-secondary,#636366);line-height:1.7;margin-bottom:20px">' +
            '月額150円で全エピソードの要約・音声が聴き放題。</p>' +
            '<a href="/pages/pricing.html#plan-pro" style="display:inline-block;background:#6b21a8;color:#fff;' +
            'font-size:0.88rem;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none">Proプランを見る</a>' +
            '</div>';
          articleBody.appendChild(gate);
        }
      }

      // 「さらに深く」セクションも完全非表示
      if (articleDeep) {
        articleDeep.style.display = 'none';
        articleDeep.setAttribute('data-pro-hidden', 'true');
      }

      // --- 音声プレイヤーのロック ---
      var playerContainer = document.getElementById('articleAudioPlayer');
      if (playerContainer) {
        // audio-player.jsのbindPlayerを阻止するため、data-locked属性をセット
        var playBtn = document.getElementById('articlePlayBtn');
        if (playBtn && playBtn.dataset.locked !== 'true') {
          playBtn.dataset.locked = 'true';
          playBtn.innerHTML = '<span class="play-icon">&#9654;</span>' +
            '<span class="lock-icon"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>';
          playBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (typeof DEEPCAST_AUTH !== 'undefined') DEEPCAST_AUTH.showUpgradeGate();
          });
        }
      }
    };

    // DEEPCAST_AUTHの初期化完了を待つ
    if (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.ready) {
      DEEPCAST_AUTH.ready.then(checkAccess);
    } else {
      // auth.jsがまだロードされていない場合はDOMContentLoadedで再試行
      document.addEventListener('DOMContentLoaded', function () {
        if (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.ready) {
          DEEPCAST_AUTH.ready.then(checkAccess);
        } else {
          checkAccess();
        }
      });
    }
  }

  // 即時実行（DOMContentLoaded前でも本文を隠すため）
  // ただしbodyがまだない場合はDOMContentLoadedで実行
  if (document.body) {
    applyProGate();
  } else {
    document.addEventListener('DOMContentLoaded', applyProGate);
  }

  // グローバルに公開（SPA遷移後の再適用用）
  window.DeepCastProGate = { apply: applyProGate };

})();
