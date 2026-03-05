// ===== Service Worker Registration (PWA) =====
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ===== DeepCast AI =====
document.addEventListener('DOMContentLoaded', () => {

  // ===== Floating Formulas (random drift) =====
  (() => {
    const container = document.querySelector('.hero-formulas');
    if (!container) return;
    const items = container.querySelectorAll('.formula');
    const w = window.innerWidth;
    const scale = Math.min(Math.max(w / 1200, 0.45), 1); // 0.45–1.0
    const minSize = Math.round(16 * scale);
    const maxSize = Math.round(26 * scale);

    const state = [];
    items.forEach((el) => {
      const size = minSize + Math.random() * (maxSize - minSize);
      const x = 5 + Math.random() * 90;   // 5%–95%
      const y = 5 + Math.random() * 90;
      const rot = -15 + Math.random() * 30;
      // random velocity (% per second)
      const vx = (0.3 + Math.random() * 0.7) * (Math.random() < 0.5 ? 1 : -1);
      const vy = (0.2 + Math.random() * 0.5) * (Math.random() < 0.5 ? 1 : -1);

      el.style.left = x + '%';
      el.style.top = y + '%';
      el.style.fontSize = Math.round(size) + 'px';
      el.style.transform = `rotate(${rot.toFixed(1)}deg)`;
      el.style.opacity = '1';

      state.push({ el, x, y, vx, vy, rot });
    });

    let last = performance.now();
    function tick(now) {
      const dt = (now - last) / 1000; // seconds
      last = now;
      for (const s of state) {
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        // bounce off edges (5%–95%)
        if (s.x < 2)  { s.x = 2;  s.vx = Math.abs(s.vx); }
        if (s.x > 95) { s.x = 95; s.vx = -Math.abs(s.vx); }
        if (s.y < 2)  { s.y = 2;  s.vy = Math.abs(s.vy); }
        if (s.y > 95) { s.y = 95; s.vy = -Math.abs(s.vy); }
        s.el.style.left = s.x + '%';
        s.el.style.top = s.y + '%';
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  })();

  // ===== Navbar Scroll =====
  const navbar = document.getElementById('navbar');
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 20);
  });

  // ===== Mobile Menu =====
  const hamburger = document.getElementById('hamburger');
  const navLinks = document.getElementById('navLinks');
  hamburger.addEventListener('click', () => navLinks.classList.toggle('active'));
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => navLinks.classList.remove('active'));
  });

  // ===== Stat Counter =====
  document.querySelectorAll('.stat-number[data-count]').forEach(el => {
    const obs = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        const target = parseInt(el.dataset.count);
        const start = performance.now();
        const tick = (now) => {
          const p = Math.min((now - start) / 1800, 1);
          el.textContent = Math.floor((1 - Math.pow(1 - p, 3)) * target).toLocaleString();
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        obs.unobserve(el);
      }
    }, { threshold: 0.5 });
    obs.observe(el);
  });


  // =========================================================
  //  AUDIO PLAYER — self-hosted, no external platforms
  //  - HTML5 <audio> element
  //  - Media Session API for lock-screen / background control
  //  - episodes.json で audio フィールドにファイルパスを指定
  //
  //  使い方:
  //    1. episodes/ に mp3 を置く (例: ep003.mp3)
  //    2. episodes.json の audio に "episodes/ep003.mp3" と書く
  //    3. サイトを開けば再生できる
  // =========================================================

  // Shared audio element
  const audioEl = new Audio();
  audioEl.preload = 'metadata';
  let currentPlayBtn = null;
  let currentTitle = '';

  // Mini player elements (may not exist on legal pages)
  const miniPlayer = document.getElementById('miniPlayer');
  const miniPlayBtn = document.getElementById('miniPlayBtn');
  const miniTitle = document.getElementById('miniTitle');
  const miniProgressFill = document.getElementById('miniProgressFill');
  const miniProgressBar = document.getElementById('miniProgressBar');
  const miniTime = document.getElementById('miniTime');
  const miniCloseBtn = document.getElementById('miniCloseBtn');

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function showMiniPlayer() {
    if (miniPlayer) {
      miniPlayer.classList.add('active');
      document.body.classList.add('player-active');
    }
  }
  function hideMiniPlayer() {
    if (miniPlayer) {
      miniPlayer.classList.remove('active');
      document.body.classList.remove('player-active');
    }
  }

  function updatePlayIcons(playing) {
    const icon = playing ? '&#10074;&#10074;' : '&#9654;';
    if (currentPlayBtn) currentPlayBtn.innerHTML = '<span class="play-icon">' + icon + '</span>';
    if (miniPlayBtn) miniPlayBtn.innerHTML = '<span class="play-icon">' + icon + '</span>';
  }

  function stopCurrent() {
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      currentPlayBtn.innerHTML = '<span class="play-icon">&#9654;</span>';
      currentPlayBtn.classList.remove('playing');
      const fill = card.querySelector('.progress-fill');
      if (fill) fill.style.width = '0%';
      currentPlayBtn = null;
    }
    audioEl.pause();
    audioEl.currentTime = 0;
    hideMiniPlayer();
  }

  // Media Session API — lock-screen & background controls
  function setMediaSession(title) {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: title,
      artist: 'DeepCast AI',
      album: 'AIポッドキャスト',
    });
    navigator.mediaSession.setActionHandler('play', () => { audioEl.play(); updatePlayIcons(true); });
    navigator.mediaSession.setActionHandler('pause', () => { audioEl.pause(); updatePlayIcons(false); });
    navigator.mediaSession.setActionHandler('stop', stopCurrent);
    navigator.mediaSession.setActionHandler('seekbackward', () => { audioEl.currentTime = Math.max(0, audioEl.currentTime - 10); });
    navigator.mediaSession.setActionHandler('seekforward', () => { audioEl.currentTime = Math.min(audioEl.duration || 0, audioEl.currentTime + 10); });
    navigator.mediaSession.setActionHandler('seekto', (d) => { if (d.seekTime != null) audioEl.currentTime = d.seekTime; });
  }

  // Mini player controls
  if (miniPlayBtn) {
    miniPlayBtn.addEventListener('click', () => {
      if (!audioEl.src) return;
      if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
      else { audioEl.pause(); updatePlayIcons(false); }
    });
  }
  if (miniCloseBtn) {
    miniCloseBtn.addEventListener('click', stopCurrent);
  }
  if (miniProgressBar) {
    miniProgressBar.addEventListener('click', (e) => {
      if (!audioEl.duration) return;
      const rect = miniProgressBar.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      audioEl.currentTime = ratio * audioEl.duration;
    });
  }

  // Global time update — syncs card player + mini player
  audioEl.addEventListener('timeupdate', () => {
    if (!audioEl.duration) return;
    const pct = (audioEl.currentTime / audioEl.duration * 100) + '%';
    const timeStr = formatTime(audioEl.currentTime) + ' / ' + formatTime(audioEl.duration);

    if (miniProgressFill) miniProgressFill.style.width = pct;
    if (miniTime) miniTime.textContent = timeStr;

    // Update card progress too
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      const fill = card.querySelector('.progress-fill');
      const timeEl = card.querySelector('.progress-time');
      if (fill) fill.style.width = pct;
      if (timeEl) timeEl.textContent = timeStr;
    }

    // Update Media Session position
    if ('mediaSession' in navigator && navigator.mediaSession.setPositionState) {
      try {
        navigator.mediaSession.setPositionState({
          duration: audioEl.duration,
          playbackRate: audioEl.playbackRate,
          position: audioEl.currentTime
        });
      } catch(e) {}
    }
  });

  audioEl.addEventListener('ended', () => {
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      currentPlayBtn.innerHTML = '<span class="play-icon">&#9654;</span>';
      currentPlayBtn.classList.remove('playing');
      const fill = card.querySelector('.progress-fill');
      if (fill) fill.style.width = '0%';
      const timeEl = card.querySelector('.progress-time');
      const dur = card.querySelector('.episode-duration');
      if (timeEl && dur) timeEl.textContent = '0:00 / ' + dur.textContent;
      currentPlayBtn = null;
    }
    updatePlayIcons(false);
    hideMiniPlayer();
  });

  function bindPlayer(btn, audioSrc, title) {
    btn.addEventListener('click', () => {
      const card = btn.closest('.episode-card');
      const timeEl = card.querySelector('.progress-time');

      // If this button is already playing → toggle pause
      if (currentPlayBtn === btn) {
        if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
        else { audioEl.pause(); updatePlayIcons(false); }
        return;
      }

      // Stop any current playback
      stopCurrent();

      if (!audioSrc) {
        if (timeEl) timeEl.textContent = '音声ファイル未設定';
        return;
      }

      currentPlayBtn = btn;
      currentTitle = title;
      audioEl.src = audioSrc;
      audioEl.play().catch(() => {
        if (timeEl) timeEl.textContent = '音声ファイルを読み込めません';
        currentPlayBtn = null;
        return;
      });

      btn.classList.add('playing');
      updatePlayIcons(true);
      setMediaSession(title);

      // Show mini player
      if (miniTitle) miniTitle.textContent = title;
      showMiniPlayer();
    });
  }


  // ===== Render Episodes from JSON =====

  function renderEpisode(ep) {
    const isFree = ep.free;
    const tags = ep.tags.map(t => `<span class="tag">${t}</span>`).join('');

    const playerHtml = isFree
      ? `<div class="episode-player">
          <button class="play-btn" data-audio="${ep.audio || ''}" data-title="${ep.title}" aria-label="再生">
            <span class="play-icon">&#9654;</span>
          </button>
          <div class="episode-progress">
            <div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div>
            <span class="progress-time">0:00 / ${ep.duration}</span>
          </div>
        </div>`
      : `<div class="episode-player locked-player">
          <button class="play-btn locked-btn" aria-label="Pro会員限定">
            <span class="lock-icon">&#128274;</span>
          </button>
          <div class="episode-progress">
            <span class="progress-time">Pro会員で再生 &#8594;</span>
          </div>
        </div>`;

    return `
      <article class="episode-card ${isFree ? '' : 'locked'}" data-category="${ep.category}">
        <div class="episode-header">
          <div class="episode-info">
            <span class="episode-badge ${isFree ? 'free' : 'pro'}">${isFree ? 'FREE' : 'PRO'}</span>
            <span class="episode-number">#${ep.id}</span>
            <span class="episode-date">${ep.date}</span>
            <span class="episode-duration">${ep.duration}</span>
          </div>
          <h3 class="episode-title">${ep.title}</h3>
          <p class="episode-desc">${ep.description}</p>
          <div class="episode-tags">${tags}</div>
        </div>
        <div class="episode-embed">${playerHtml}</div>
      </article>`;
  }

  const episodeList = document.getElementById('episodeList');

  function loadEpisodes(episodes) {
    if (!episodes.length) {
      episodeList.innerHTML = '<p class="loading-text">エピソードはまだありません。</p>';
      return;
    }
    episodeList.innerHTML = episodes.map(renderEpisode).join('');

    // Bind audio players
    episodeList.querySelectorAll('.play-btn:not(.locked-btn)').forEach(btn => {
      bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
    });
    episodeList.querySelectorAll('.locked-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        openModal('Pro プランに登録', '全エピソード聴き放題＋月3回リクエスト。');
      });
    });

    initFilters();
    initReveal();
  }

  // Daily rotation: pick 3 free + 2 pro based on today's date
  function getDailySeed() {
    const now = new Date();
    return now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();
  }

  function seededShuffle(arr, seed) {
    const copy = arr.slice();
    let s = seed;
    for (let i = copy.length - 1; i > 0; i--) {
      s = (s * 9301 + 49297) % 233280;
      const j = Math.floor((s / 233280) * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }

  function pickDailyEpisodes(episodes) {
    const seed = getDailySeed();
    const freeEps = episodes.filter(ep => ep.free);
    const proEps = episodes.filter(ep => !ep.free);
    const shuffledFree = seededShuffle(freeEps, seed);
    const shuffledPro = seededShuffle(proEps, seed + 1);
    return [...shuffledFree.slice(0, 3), ...shuffledPro.slice(0, 2)];
  }

  fetch('episodes/episodes.json')
    .then(r => r.json())
    .then(episodes => loadEpisodes(pickDailyEpisodes(episodes)))
    .catch(() => {
      const fallback = [
        { id: 3, title: "GPT-5 vs Gemini 2.5：次世代AIの覇権争い", description: "OpenAIとGoogleの最新モデル比較。", date: "2026.03.02", category: "tech", tags: ["AI", "テクノロジー"], duration: "5:12", free: true, audio: "" },
        { id: 2, title: "スタートアップ資金調達の新常識 2026", description: "VC市場の変化、AIスタートアップへの投資トレンド。", date: "2026.03.01", category: "business", tags: ["ビジネス"], duration: "4:58", free: true, audio: "" },
        { id: 1, title: "量子コンピュータの実用化が見えてきた", description: "IBMとGoogleの量子超越性競争。実用化のユースケース。", date: "2026.02.28", category: "science", tags: ["サイエンス"], duration: "5:31", free: false, audio: "" }
      ];
      loadEpisodes(fallback);
    });


  // ===== Episode Filters =====
  function initFilters() {
    const btns = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.episode-card');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        btns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        cards.forEach(c => {
          c.style.display = (btn.dataset.filter === 'all' || c.dataset.category === btn.dataset.filter) ? '' : 'none';
        });
      });
    });
  }


  // ===== Pricing Toggle =====
  const pricingToggle = document.getElementById('pricingToggle');
  const toggleLabels = document.querySelectorAll('.toggle-label');
  let isYearly = false;
  pricingToggle.addEventListener('click', () => {
    isYearly = !isYearly;
    pricingToggle.classList.toggle('active', isYearly);
    toggleLabels.forEach(l => l.classList.toggle('active', (l.dataset.period === 'yearly') === isYearly));
    document.querySelectorAll('.monthly-price,.monthly-period').forEach(e => e.style.display = isYearly ? 'none' : '');
    document.querySelectorAll('.yearly-price,.yearly-period').forEach(e => e.style.display = isYearly ? '' : 'none');
  });


  // ===== FAQ =====
  document.querySelectorAll('.faq-item').forEach(item => {
    item.querySelector('.faq-question').addEventListener('click', () => {
      const wasActive = item.classList.contains('active');
      document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('active'));
      if (!wasActive) item.classList.add('active');
    });
  });


  // ===== Modal =====
  const modal = document.getElementById('signupModal');
  const modalTitle = document.getElementById('modalTitle');
  const modalDesc = document.getElementById('modalDesc');

  function openModal(title, desc) {
    modalTitle.textContent = title || '無料で始める';
    modalDesc.textContent = desc || 'メールアドレスで簡単登録';
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
  document.getElementById('modalClose').addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  let currentPlan = null;

  document.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      const msgs = {
        'signup-free':     ['無料で始める', 'メールアドレスで簡単登録。', 'free'],
        'signup-pro':      ['Pro プランに登録', '全エピソード聴き放題＋月3回リクエスト。', 'pro'],
        'signup-business': ['Business プランに登録', 'リクエスト無制限。', 'business'],
        'contact':         ['お問い合わせ', 'ご質問・ご相談はこちらから。', null]
      };
      const m = msgs[btn.dataset.action];
      if (m) {
        currentPlan = m[2];
        openModal(m[0], m[1]);
      }
    });
  });

  // Signup form — Ajax submit
  document.getElementById('signupForm').addEventListener('submit', e => {
    e.preventDefault();
    const emailVal = document.getElementById('email').value;
    const btn = e.target.querySelector('button[type="submit"]');
    btn.textContent = '登録中...';
    btn.disabled = true;

    const planName = currentPlan || 'free';
    fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ email: emailVal, plan: planName, _subject: 'DeepCast AI 新規会員登録 (' + planName + ')', _captcha: 'false' })
    })
    .then(r => r.json())
    .then(() => {
      // Save member info
      localStorage.setItem('deepcast_member', JSON.stringify({
        email: emailVal,
        plan: planName,
        registered: new Date().toISOString()
      }));

      const isPaid = planName === 'pro' || planName === 'business';
      e.target.innerHTML = '<div style="text-align:center;padding:24px 0">' +
        '<div style="font-size:24px;margin-bottom:8px">&#10003;</div>' +
        '<h3 style="font-size:17px;font-weight:600;margin-bottom:4px">登録完了</h3>' +
        '<p style="color:var(--text-secondary);font-size:13px">' + emailVal + ' で登録しました。</p>' +
        (isPaid ? '<p style="font-size:13px;margin-top:12px">全エピソードページへ移動します...</p>' : '') +
        '</div>';

      if (isPaid) {
        setTimeout(() => { window.location.href = 'all-episodes.html'; }, 2000);
      } else {
        setTimeout(closeModal, 3000);
      }
    })
    .catch(() => {
      btn.textContent = '登録に失敗しました';
      setTimeout(() => { btn.textContent = '無料で登録する'; btn.disabled = false; }, 2000);
    });
  });


  // ===== Request Form =====
  const reqForm = document.getElementById('requestForm');
  if (reqForm) {
    reqForm.addEventListener('submit', e => {
      e.preventDefault();
      const data = new FormData(reqForm);
      const body = {
        topic: data.get('topic'),
        category: data.get('category'),
        depth: data.get('depth'),
        detail: data.get('detail'),
        email: data.get('email'),
        _subject: 'DeepCast AI 新規リクエスト',
        _captcha: 'false'
      };
      const btn = reqForm.querySelector('button[type="submit"]');
      const origText = btn.textContent;
      btn.textContent = '送信中...';
      btn.disabled = true;
      fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      })
      .then(r => r.json())
      .then(() => {
        btn.textContent = '受付完了!';
        btn.style.background = '#3a8a44';
        setTimeout(() => {
          reqForm.reset();
          btn.textContent = origText;
          btn.style.background = '';
          btn.disabled = false;
        }, 3000);
      })
      .catch(() => {
        btn.textContent = '送信に失敗しました';
        setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 2000);
      });
    });
  }

  document.querySelectorAll('.popular-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      const f = document.getElementById('requestTopic');
      if (f) { f.value = tag.dataset.topic; f.focus(); f.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    });
  });


  // ===== SNS Coming Soon =====
  document.querySelectorAll('.sns-coming-soon').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const toast = document.createElement('div');
      toast.textContent = 'SNSアカウントは準備中です';
      toast.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:12px 24px;border-radius:8px;font-size:14px;z-index:9999;opacity:0;transition:opacity .3s';
      document.body.appendChild(toast);
      requestAnimationFrame(() => toast.style.opacity = '1');
      setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
    });
  });

  // ===== Smooth Scroll =====
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href === '#' || href === '') return;
      const t = document.querySelector(href);
      if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth' }); }
    });
  });


  // ===== Reveal =====
  function initReveal() {
    const els = document.querySelectorAll(
      '.episode-card,.service-card,.step-card,.pricing-card,.testimonial-card,.faq-item,.request-form-card,.request-info-card'
    );
    const obs = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting) {
          en.target.style.opacity = '1';
          en.target.style.transform = 'translateY(0)';
          obs.unobserve(en.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });
    els.forEach((el, i) => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(12px)';
      el.style.transition = `opacity 0.4s ease ${(i%3)*0.06}s, transform 0.4s ease ${(i%3)*0.06}s`;
      obs.observe(el);
    });
  }

  // Static elements reveal
  const sEls = document.querySelectorAll('.service-card,.step-card,.pricing-card,.testimonial-card,.faq-item,.request-form-card,.request-info-card');
  const sObs = new IntersectionObserver(entries => {
    entries.forEach(en => { if (en.isIntersecting) { en.target.style.opacity='1'; en.target.style.transform='translateY(0)'; sObs.unobserve(en.target); }});
  }, { threshold: 0.08, rootMargin: '0px 0px -30px 0px' });
  sEls.forEach((el,i) => { el.style.opacity='0'; el.style.transform='translateY(12px)'; el.style.transition=`opacity 0.4s ease ${(i%3)*0.06}s, transform 0.4s ease ${(i%3)*0.06}s`; sObs.observe(el); });

});
