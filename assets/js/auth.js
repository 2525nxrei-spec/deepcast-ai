/**
 * DeepCast — フロントエンド認証ライブラリ
 * JWT管理・ログイン状態チェック・Pro判定・エピソード制限
 */

const DEEPCAST_AUTH = (() => {
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
    return !!getToken();
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
      response = await fetch(`${API_BASE}${endpoint}`, options);
    } catch (err) {
      console.error('[DEEPCAST_AUTH] ネットワークエラー:', err);
      throw new Error('ネットワーク接続を確認してください');
    }

    let data;
    try {
      data = await response.json();
    } catch {
      console.error('[DEEPCAST_AUTH] レスポンスのJSON解析に失敗');
      throw new Error('サーバーからの応答が不正です');
    }

    // トークン期限切れ（401）→ 自動ログアウト
    if (response.status === 401) {
      console.error('[DEEPCAST_AUTH] トークン期限切れ');
      removeToken();
      updateNavUI();
      throw new Error('セッションが切れました。再ログインしてください');
    }

    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'リクエストに失敗しました');
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
    removeToken();
    window.location.href = '/';
  }

  async function fetchMe() {
    try {
      const data = await apiRequest('/api/auth/me');
      setUser(data.user);
      return data.user;
    } catch {
      removeToken();
      return null;
    }
  }

  // --- Stripe ---

  async function startCheckout() {
    const data = await apiRequest('/api/stripe/checkout', 'POST');
    if (data.checkout_url) {
      window.location.href = data.checkout_url;
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
          <a href="/pages/pricing.html" style="display:inline-block;background:#6b21a8;color:#fff;font-size:0.88rem;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none;margin-bottom:12px">Proプランを見る</a>
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
  }

  // --- ナビバーUI更新 ---

  function updateNavUI() {
    const user = getUser();
    const navLinks = document.querySelector('.nav__links');
    if (!navLinks) return;

    // 既存の認証リンクがあれば削除
    const existingLink = navLinks.querySelector('.nav__auth-link');
    if (existingLink) existingLink.remove();

    const link = document.createElement('a');
    link.className = 'nav__link nav__auth-link';

    if (user) {
      link.href = '/pages/account.html';
      link.textContent = user.plan === 'pro' ? 'Pro' : 'アカウント';
      if (user.plan === 'pro') {
        link.style.cssText = 'color:#6b21a8;font-weight:700';
      }
    } else {
      link.href = '/pages/pricing.html';
      link.textContent = 'ログイン';
    }

    // ドロップダウンの前に挿入
    const dropdown = navLinks.querySelector('.nav__dropdown');
    if (dropdown) {
      navLinks.insertBefore(link, dropdown);
    } else {
      navLinks.appendChild(link);
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

  return {
    getToken, getUser, isLoggedIn, isPro,
    register, login, logout, fetchMe,
    startCheckout, openPortal, getBillingStatus,
    canAccessEpisode, showUpgradeGate,
    updateNavUI, init,
  };
})();

// ページロード時に自動初期化
document.addEventListener('DOMContentLoaded', () => {
  DEEPCAST_AUTH.init();
});
