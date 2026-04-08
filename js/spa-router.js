// ===================================================================
//  DeepCast AI - SPA Router
//  ページ遷移、コンテンツ差し替え、履歴管理、メタ情報更新
// ===================================================================

(function () {
  'use strict';

  var DA = window.DeepCastAudio;
  var DP = window.DeepCastPage;

  // SPA対象外のファイル拡張子
  var NON_SPA_EXT = ['.mp3', '.wav', '.ogg', '.mp4', '.pdf', '.zip', '.xml', '.json', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico'];

  // SPA対象外のパス（独自スクリプトを持つ独立ページ）
  // pages/ 配下: login, pricing, account — nav.navbar構造を持たず、
  // auth.js / Stripe.js 等の独自スクリプトが必要なため通常遷移させる
  var NON_SPA_PATHS = ['/pages/'];

  function isSPALink(anchor) {
    try {
      var url = new URL(anchor.href, location.origin);
      if (url.origin !== location.origin) return false;
    } catch(e) { return false; }
    if (anchor.target && anchor.target !== '_self') return false;
    if (anchor.hasAttribute('download')) return false;
    var pathname = new URL(anchor.href, location.origin).pathname;
    // pages/ 配下は独自スクリプトを持つ独立ページのため SPA 対象外
    for (var i = 0; i < NON_SPA_PATHS.length; i++) {
      if (pathname.indexOf(NON_SPA_PATHS[i]) !== -1) return false;
    }
    for (var i = 0; i < NON_SPA_EXT.length; i++) {
      if (pathname.toLowerCase().endsWith(NON_SPA_EXT[i])) return false;
    }
    var lastSegment = pathname.split('/').pop();
    if (lastSegment && lastSegment.indexOf('.') !== -1 && !lastSegment.endsWith('.html')) return false;
    return true;
  }

  function parseHTML(html) {
    var parser = new DOMParser();
    return parser.parseFromString(html, 'text/html');
  }

  // nav〜mini-player間のコンテンツを抽出
  function getSwapContent(doc) {
    var body = doc.body;
    var nav = body.querySelector('nav.navbar');
    var miniPlayer = body.querySelector('.mini-player');
    var contentNodes = [];
    var collecting = false;
    for (var i = 0; i < body.childNodes.length; i++) {
      var node = body.childNodes[i];
      if (node === nav) { collecting = true; continue; }
      if (node.nodeType === 1 && node.classList && node.classList.contains('mini-player')) { collecting = false; continue; }
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') continue;
      if (collecting) contentNodes.push(node.cloneNode(true));
    }
    return contentNodes;
  }

  function getNavContent(doc) {
    var nav = doc.body.querySelector('nav.navbar');
    return nav ? nav.innerHTML : null;
  }

  function getPageStyles(doc) {
    var styles = doc.head.querySelectorAll('style');
    return Array.from(styles).map(function(s) { return s.outerHTML; }).join('\n');
  }

  // メタ情報の抽出
  function extractMeta(doc) {
    var get = function(sel, attr) {
      var el = doc.head.querySelector(sel);
      return el ? el.getAttribute(attr) : null;
    };
    return {
      description:   get('meta[name="description"]', 'content'),
      ogTitle:       get('meta[property="og:title"]', 'content'),
      ogDescription: get('meta[property="og:description"]', 'content'),
      ogUrl:         get('meta[property="og:url"]', 'content'),
      canonical:     get('link[rel="canonical"]', 'href')
    };
  }

  // metaタグの更新・作成
  function setMeta(selector, attr, value) {
    if (value == null) return;
    var el = document.head.querySelector(selector);
    if (el) {
      el.setAttribute(attr, value);
    } else {
      el = document.createElement(selector.startsWith('link') ? 'link' : 'meta');
      var matches = selector.match(/\[(\w[\w-]*)="([^"]+)"\]/g);
      if (matches) {
        matches.forEach(function(m) {
          var parts = m.match(/\[(\w[\w-]*)="([^"]+)"\]/);
          el.setAttribute(parts[1], parts[2]);
        });
      }
      el.setAttribute(attr, value);
      document.head.appendChild(el);
    }
  }

  function applyMeta(meta) {
    if (!meta) return;
    setMeta('meta[name="description"]',        'content', meta.description);
    setMeta('meta[property="og:title"]',       'content', meta.ogTitle);
    setMeta('meta[property="og:description"]', 'content', meta.ogDescription);
    setMeta('meta[property="og:url"]',         'content', meta.ogUrl);
    setMeta('link[rel="canonical"]',           'href',    meta.canonical);
  }

  // DOMの差し替え実行
  function applySwap(contentNodes, pageStyles, title, navHTML, meta) {
    document.title = title;
    applyMeta(meta);

    // 既存のページ固有スタイルを除去
    document.querySelectorAll('style[data-spa-page]').forEach(function(s) { s.remove(); });

    if (pageStyles) {
      var styleContainer = document.createElement('div');
      styleContainer.innerHTML = pageStyles;
      Array.from(styleContainer.children).forEach(function(s) {
        s.setAttribute('data-spa-page', 'true');
        document.head.appendChild(s);
      });
    }

    if (navHTML) {
      var nav = document.querySelector('nav.navbar');
      if (nav) nav.innerHTML = navHTML;
    }

    var spaContent = document.getElementById('spaContent');
    if (spaContent) {
      spaContent.innerHTML = '';
      contentNodes.forEach(function(node) { spaContent.appendChild(node); });
    }
  }

  // =========================================================
  //  SPA遷移
  // =========================================================
  var isNavigating = false;

  function navigateTo(url, pushState) {
    if (isNavigating) return;
    isNavigating = true;

    document.body.style.opacity = '0.7';
    document.body.style.transition = 'opacity 0.15s';

    fetch(url)
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function(html) {
        var doc = parseHTML(html);
        var contentNodes = getSwapContent(doc);
        var pageStyles = getPageStyles(doc);
        var title = doc.title;
        var navHTML = getNavContent(doc);
        var meta = extractMeta(doc);

        applySwap(contentNodes, pageStyles, title, navHTML, meta);

        // 遷移先のbody属性を反映（Pro記事ゲーティング用）
        var newTier = doc.body.dataset.tier || '';
        if (newTier) {
          document.body.dataset.tier = newTier;
        } else {
          delete document.body.dataset.tier;
        }

        if (pushState !== false) {
          history.pushState({ spa: true }, title, url);
        }

        document.body.style.opacity = '1';
        isNavigating = false;

        DP.reinitPage();

        // Pro記事ゲーティングを再適用
        if (window.DeepCastProGate) {
          window.DeepCastProGate.apply();
        }
      })
      .catch(function(err) {
        document.body.style.opacity = '1';
        isNavigating = false;
        location.href = url;
      });
  }

  // リンククリックのインターセプト
  document.addEventListener('click', function(e) {
    var anchor = e.target.closest('a');
    if (!anchor) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.defaultPrevented) return;

    var href = anchor.getAttribute('href');
    if (!href) return;

    // 他ページへのハッシュリンク
    if (href.includes('#') && !href.startsWith('#')) {
      var hashPart = href.split('#')[1];
      try {
        var linkUrl = new URL(href, location.href);
        if (linkUrl.pathname === location.pathname) {
          e.preventDefault();
          var target = document.getElementById(hashPart);
          if (target) target.scrollIntoView({ behavior: 'smooth' });
          return;
        }
      } catch(ex) {}
    }

    if (href.startsWith('#')) return;
    if (!isSPALink(anchor)) return;

    try {
      var linkUrl2 = new URL(href, location.href);
      if (linkUrl2.origin !== location.origin) return;
      e.preventDefault();
      navigateTo(linkUrl2.href, true);
    } catch(ex) {}
  });

  // ブラウザの戻る/進む
  window.addEventListener('popstate', function(e) {
    navigateTo(location.href, false);
  });

  // スクロールによるナビバー表示切替
  window.addEventListener('scroll', function() {
    var navbar = document.getElementById('navbar');
    if (!navbar) return;
    var isIndex = (function() { var p = location.pathname.replace(/\/index\.html$/, '/'); return p.endsWith('/') || p === ''; })();
    if (isIndex) {
      navbar.classList.toggle('scrolled', window.scrollY > 20);
    }
  });

  // =========================================================
  //  初期ページセットアップ
  // =========================================================
  function setupInitialPage() {
    if (document.getElementById('spaContent')) {
      DA.bindMiniPlayer();
      DP.reinitPage();
      return;
    }

    var body = document.body;
    var nav = body.querySelector('nav.navbar');
    var miniPlayer = body.querySelector('.mini-player');

    if (!nav || !miniPlayer) {
      DA.bindMiniPlayer();
      return;
    }

    // spaContentラッパーを作成し、nav〜miniPlayer間のノードを移動
    var wrapper = document.createElement('div');
    wrapper.id = 'spaContent';

    var nodesToMove = [];
    var collecting = false;
    for (var i = 0; i < body.childNodes.length; i++) {
      var node = body.childNodes[i];
      if (node === nav) { collecting = true; continue; }
      if (node === miniPlayer) { collecting = false; continue; }
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') continue;
      if (collecting) nodesToMove.push(node);
    }

    nav.insertAdjacentElement('afterend', wrapper);
    nodesToMove.forEach(function(node) { wrapper.appendChild(node); });

    DA.bindMiniPlayer();
    DP.reinitPage();
  }

  // DOM読み込み完了時に実行
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupInitialPage);
  } else {
    setupInitialPage();
  }

  // グローバルに公開（audio-player.jsのended内から遷移に使用）
  window.DeepCastRouter = {
    navigateTo: navigateTo
  };

})();
