/**
 * DeepCast — フロントエンド認証ライブラリ
 * JWT管理・ログイン状態チェック・Pro判定・エピソード制限
 */

const DEEPCAST_AUTH = (() => {
  // 空文字 = 同一オリ���ン（Cloudflare Pages Functions）への相対パスリクエスト
  // 本番: deepcast-ai.com/api/... / ローカル: localhost:8788/api/...
  const API_BASE = '';
  const TOKEN_KEY = 'deepcast_token';
  const USER_KEY = 'deepcast_user';

  // --- トークン管理 ---

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function removeToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getUser() {
    try {
      const data = localStorage.getItem(USER_KEY);
      return data ? JSON.parse(data) : null;
    } catch {
      return null;
    }
  }

  function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function isLoggedIn() {
    const token = getToken();
    if (!token) return false;

    // JWTのexp（有効期限）を検証
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        // 期限切れ → トークンを削除してfalseを返す
        removeToken();
        return false;
      }
    } catch {
      // デコード失敗 → 不正なトークンとして削除
      removeToken();
      return false;
    }

    return true;
  }

  function isPro() {
    const user = getUser();
    return user && user.plan === 'pro';
  }

  // --- API通信 ---

  async function apiRequest(endpoint, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);

    let response;
    try {
      // 15秒タイムアウト（ボタンが永久にスタックするのを防止）
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      options.signal = controller.signal;
      response = await fetch(`${API_BASE}${endpoint}`, options);
      clearTimeout(timeoutId);
    } catch (err) {
      console.error('[DEEPCAST_AUTH] ネットワークエラー:', err);
      if (err.name === 'AbortError') {
        throw new Error('サーバーからの応答がありません。しばらく時間をおいて再度お試しください。');
      }
      throw new Error('インターネット接続を確認してください。接続に問題がない場合は、しばらく時間をおいて再度お試しください。');
    }

    let data;
    try {
      data = await response.json();
    } catch {
      console.error('[DEEPCAST_AUTH] レスポンスのJSON解析に失敗');
      throw new Error('サーバーからの応答が不正です。しばらく時間をおいて再度お試しください。');
    }

    // トークン期限切れ（401）→ 自動ログアウト
    if (response.status === 401) {
      console.error('[DEEPCAST_AUTH] トークン期限切れ');
      removeToken();
      updateNavUI();
      throw new Error('セッションの有効期限が切れました。お手数ですが、再度ログインしてください。');
    }

    if (response.status === 429) {
      throw new Error('リクエストが多すぎます。しばらく時間をおいてから再度お試しください。');
    }

    if (response.status >= 500) {
      const serverMsg = data && data.error ? data.error : '';
      console.error('[DEEPCAST_AUTH] サーバーエラー:', response.status, serverMsg);
      throw new Error(serverMsg || 'サーバーに一時的な問題が発生しています。しばらく時間をおいて再度お試しください。');
    }

    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'リクエストに失敗しました。もう一度お試しください。');
    }
    return data;
  }

  // --- 認証 ---

  async function register(email, password, displayName) {
    const data = await apiRequest('/api/auth/register', 'POST', {
      email, password, display_name: displayName,
    });
    setToken(data.token);
    setUser(data.user);
    updateNavUI();
    return data.user;
  }

  async function login(email, password) {
    const data = await apiRequest('/api/auth/login', 'POST', { email, password });
    setToken(data.token);
    setUser(data.user);
    updateNavUI();
    return data.user;
  }

  function logout() {
    if (!confirm('ログアウトしますか？')) return;
    // ステートレスJWT方式のため、クライアント側のトークン削除で無効化
    // サーバーサイドのトークン無効化リスト（ブラックリスト）は未実装
    // httpOnly cookieは使用していないため、localStorage削除のみで十分
    removeToken();
    localStorage.removeItem('deepcast_last_activity');
    window.location.href = '/';
  }

  async function fetchMe() {
    try {
      const data = await apiRequest('/api/auth/me');
      setUser(data.user);
      return data.user;
    } catch (err) {
      // 401（トークン無効/期限切れ）はapiRequest内でremoveToken済み
      // ネットワークエラー等ではトークンを消さない（一時的な接続障害で強制ログアウトしない）
      const msg = err.message || '';
      if (msg.includes('セッションの有効期限が切れました')) {
        // 既にapiRequestでremoveToken済み
      }
      return null;
    }
  }

  // --- Stripe ---

  async function startCheckout() {
    const data = await apiRequest('/api/stripe/checkout', 'POST');
    // リダイレクト型: サーバーから返されたStripe Checkout URLに遷移
    if (data.url) {
      window.location.href = data.url;
    } else {
      throw new Error('決済セッションの作成に失敗しました。しばらく時間をおいて再度お試しください。');
    }
  }

  async function openPortal() {
    const data = await apiRequest('/api/stripe/portal', 'POST');
    if (data.portal_url) {
      window.location.href = data.portal_url;
    }
  }

  async function getBillingStatus() {
    return await apiRequest('/api/billing/status');
  }

  // --- エピソード制限 ---
  // Freeユーザーは最新3本のみ再生可能
  // episodes.jsonは新しい順ソート前提、index 0が最新

  function canAccessEpisode(episodeIndex) {
    if (isPro()) return true;
    return episodeIndex < 3;
  }

  function showUpgradeGate() {
    // 既存モーダルがあれば削除
    const existing = document.getElementById('deepcast-upgrade-gate');
    if (existing) existing.remove();

    const gate = document.createElement('div');
    gate.id = 'deepcast-upgrade-gate';
    gate.innerHTML = `
      <div style="position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;padding:20px">
        <div style="background:#fff;border-radius:8px;padding:40px 32px;max-width:420px;width:100%;text-align:center;font-family:'Noto Sans JP',sans-serif">
          <div style="width:48px;height:48px;border-radius:8px;background:#e8e0f0;display:flex;align-items:center;justify-content:center;margin:0 auto 16px">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b21a8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <h2 style="font-size:1.15rem;font-weight:700;margin-bottom:8px;color:#1d1d1f">このエピソードはProプラン限定です</h2>
          <p style="font-size:0.88rem;color:#636366;line-height:1.7;margin-bottom:24px">月額150円で全エピソード聴き放題。<br>最新のAIニュースを深掘りで、いつでもどこでも。</p>
          <a href="/pages/pricing.html#plan-pro" style="display:inline-block;background:#6b21a8;color:#fff;font-size:0.88rem;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;margin-bottom:12px">Proプランを見る</a>
          <br>
          <button id="deepcast-gate-close" style="font-size:0.8rem;color:#8e8e93;background:none;border:none;cursor:pointer;padding:8px;margin-top:4px">閉じる</button>
        </div>
      </div>
    `;
    document.body.appendChild(gate);

    // 閉じるボタン
    document.getElementById('deepcast-gate-close').addEventListener('click', () => {
      gate.remove();
    });

    // オーバーレイクリックで閉じる
    gate.firstElementChild.addEventListener('click', (e) => {
      if (e.target === gate.firstElementChild) gate.remove();
    });

    // Escキーで閉じる
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        gate.remove();
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  }

  // --- ナビバーUI更新 ---

  function updateNavUI() {
    const user = getUser();

    // navLoginBtn（ボタン型）の更新
    const navLoginBtn = document.getElementById('navLoginBtn');
    if (navLoginBtn) {
      if (user) {
        navLoginBtn.href = '/pages/account.html';
        navLoginBtn.textContent = user.plan === 'pro' ? 'Pro' : 'アカウント';
        if (user.plan === 'pro') {
          navLoginBtn.style.cssText = 'color:#6b21a8;font-weight:700';
        }
      } else {
        navLoginBtn.href = '/pages/login.html';
        navLoginBtn.textContent = 'ログイン';
        navLoginBtn.style.cssText = '';
      }
    }

    // navLoginLink（モバイルメニュー用テキストリンク）の更新
    const navLoginLink = document.getElementById('navLoginLink');
    if (navLoginLink) {
      if (user) {
        navLoginLink.href = '/pages/account.html';
        navLoginLink.textContent = user.plan === 'pro' ? 'Pro' : 'アカウント';
      } else {
        navLoginLink.href = '/pages/login.html';
        navLoginLink.textContent = 'ログイン';
      }
    }
  }

  // --- 初期化 ---

  async function init() {
    if (!getToken()) {
      updateNavUI();
      return;
    }

    try {
      await fetchMe();
    } catch (err) {
      console.error('[DEEPCAST_AUTH] 初期化時のユーザー取得失敗:', err);
    }

    updateNavUI();
  }

  // init()のPromiseを保持（他スクリプトがawaitで完了待ちできるように）
  let _initPromise = null;

  return {
    getToken, getUser, isLoggedIn, isPro,
    register, login, logout, fetchMe,
    startCheckout, openPortal, getBillingStatus,
    canAccessEpisode, showUpgradeGate,
    updateNavUI, init,
    /** init()完了を待つためのPromise。init()呼び出し後に利用可能 */
    get ready() { return _initPromise || Promise.resolve(); },
    _setInitPromise(p) { _initPromise = p; },
  };
})();

// ページロード時に自動初期化
document.addEventListener('DOMContentLoaded', () => {
  const p = DEEPCAST_AUTH.init();
  DEEPCAST_AUTH._setInitPromise(p);

  // セッションタイムアウト（24時間操作なしでログアウト）
  // 全ページで動作するようauth.jsに配置
  (function() {
    var TIMEOUT = 24 * 60 * 60 * 1000; // 24時間
    var LAST_KEY = 'deepcast_last_activity';
    function resetTimer() { localStorage.setItem(LAST_KEY, Date.now()); }
    function checkTimeout() {
      var last = parseInt(localStorage.getItem(LAST_KEY) || '0', 10);
      if (last && Date.now() - last > TIMEOUT && localStorage.getItem('deepcast_token')) {
        localStorage.removeItem('deepcast_token');
        localStorage.removeItem('deepcast_user');
        localStorage.removeItem(LAST_KEY);
        // ログインページ自身にいる場合はリダイレクトしない（ループ防止）
        if (window.location.pathname !== '/pages/login.html') {
          alert('長時間操作がなかったため、セキュリティのためログアウトしました。');
          window.location.href = '/pages/login.html';
        }
      }
    }
    if (DEEPCAST_AUTH.isLoggedIn()) {
      checkTimeout();
      resetTimer();
      ['click', 'keydown', 'scroll', 'touchstart'].forEach(function(e) {
        document.addEventListener(e, resetTimer, { passive: true });
      });
    }
  })();
});
