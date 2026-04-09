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
      // 未ログイン → ログインページにリダイレクト（Proページ自体に入れない）
      var isLoggedIn = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.isLoggedIn());
      if (!isLoggedIn) {
        window.location.href = '/pages/login.html?return=' + encodeURIComponent(window.location.pathname);
        return;
      }

      var userIsPro = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.isPro());
      if (userIsPro) return; // Proユーザーはそのまま

      // Freeユーザー → 料金ページにリダイレクト（Proページ自体を見せない）
      window.location.href = '/pages/pricing.html#plan-pro';
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
