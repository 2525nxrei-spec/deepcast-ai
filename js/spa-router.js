// ===================================================================
//  SPA Router + Persistent Audio Player
//  - Intercepts internal link clicks, fetches pages via fetch()
//  - Swaps content between nav and footer (preserving mini player)
//  - Keeps audio element alive across navigations
//  - Handles popstate (browser back/forward)
// ===================================================================

(function () {
  'use strict';

  // ===== iOS Safari audio unlock =====
  let unlocked = false;
  function unlockAudio() {
    if (unlocked) return;
    unlocked = true;
    const a = new Audio();
    a.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
    a.play().then(() => a.pause()).catch(() => {});
    document.removeEventListener('touchstart', unlockAudio, true);
    document.removeEventListener('click', unlockAudio, true);
  }
  document.addEventListener('touchstart', unlockAudio, true);
  document.addEventListener('click', unlockAudio, true);

  // ===== Service Worker =====
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }

  // =========================================================
  //  PERSISTENT AUDIO PLAYER
  // =========================================================
  const audioEl = new Audio();
  audioEl.preload = 'metadata';

  let currentPlayBtn = null;
  let currentAudioSrc = '';
  let currentTitleText = '';
  let playlist = [];
  let playlistIndex = -1;

  // Expose globally so page scripts can use it
  window.DeepCastAudio = {
    audioEl,
    get currentPlayBtn() { return currentPlayBtn; },
    set currentPlayBtn(v) { currentPlayBtn = v; },
    get playlist() { return playlist; },
    set playlist(v) { playlist = v; },
    get playlistIndex() { return playlistIndex; },
    set playlistIndex(v) { playlistIndex = v; },
    bindPlayer,
    buildPlaylist,
    stopCurrent,
    formatTime,
    resetCardUI,
    showMiniPlayer,
    hideMiniPlayer,
    updatePlayIcons,
    playFromPlaylist,
    setMediaSession
  };

  function getMiniEl(id) {
    return document.getElementById(id);
  }

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m + ':' + s.toString().padStart(2, '0');
  }

  function showMiniPlayer() {
    const mp = getMiniEl('miniPlayer');
    if (mp) { mp.classList.add('active'); document.body.classList.add('player-active'); }
  }
  function hideMiniPlayer() {
    const mp = getMiniEl('miniPlayer');
    if (mp) { mp.classList.remove('active'); document.body.classList.remove('player-active'); }
  }

  function updatePlayIcons(playing) {
    const icon = playing ? '&#10074;&#10074;' : '&#9654;';
    if (currentPlayBtn) currentPlayBtn.innerHTML = '<span class="play-icon">' + icon + '</span>';
    const mpb = getMiniEl('miniPlayBtn');
    if (mpb) mpb.innerHTML = '<span class="play-icon">' + icon + '</span>';
  }

  function resetCardUI(btn) {
    if (!btn) return;
    const card = btn.closest('.episode-card');
    if (!card) return;
    btn.innerHTML = '<span class="play-icon">&#9654;</span>';
    btn.classList.remove('playing');
    const fill = card.querySelector('.progress-fill');
    if (fill) fill.style.width = '0%';
  }

  function stopCurrent() {
    resetCardUI(currentPlayBtn);
    currentPlayBtn = null;
    currentAudioSrc = '';
    currentTitleText = '';
    playlistIndex = -1;
    audioEl.pause();
    audioEl.currentTime = 0;
    hideMiniPlayer();
  }

  function setMediaSession(title) {
    if (!('mediaSession' in navigator)) return;
    // Use absolute URL for lock screen artwork (relative paths fail on some devices)
    var base = location.origin + '/';
    navigator.mediaSession.metadata = new MediaMetadata({
      title: title, artist: 'DeepCast AI', album: 'AI\u30dd\u30c3\u30c9\u30ad\u30e3\u30b9\u30c8',
      artwork: [
        { src: base + 'assets/cover-podcast.svg', sizes: '512x512', type: 'image/svg+xml' },
        { src: base + 'assets/icon.svg', sizes: '96x96', type: 'image/svg+xml' }
      ]
    });
    navigator.mediaSession.setActionHandler('play', () => { audioEl.play(); updatePlayIcons(true); });
    navigator.mediaSession.setActionHandler('pause', () => { audioEl.pause(); updatePlayIcons(false); });
    navigator.mediaSession.setActionHandler('stop', stopCurrent);
    navigator.mediaSession.setActionHandler('seekbackward', () => { audioEl.currentTime = Math.max(0, audioEl.currentTime - 10); });
    navigator.mediaSession.setActionHandler('seekforward', () => { audioEl.currentTime = Math.min(audioEl.duration || 0, audioEl.currentTime + 10); });
    navigator.mediaSession.setActionHandler('seekto', (d) => { if (d.seekTime != null) audioEl.currentTime = d.seekTime; });
    navigator.mediaSession.setActionHandler('previoustrack', playPrev);
    navigator.mediaSession.setActionHandler('nexttrack', playNext);
  }

  function playNext() {
    if (playlist.length === 0) return;
    const nextIdx = playlistIndex + 1;
    if (nextIdx < playlist.length) playFromPlaylist(nextIdx);
    else stopCurrent();
  }

  function playPrev() {
    if (playlist.length === 0) return;
    if (audioEl.currentTime > 3 && playlistIndex >= 0) { audioEl.currentTime = 0; return; }
    const prevIdx = playlistIndex - 1;
    if (prevIdx >= 0) playFromPlaylist(prevIdx);
    else audioEl.currentTime = 0;
  }

  function playFromPlaylist(idx) {
    if (idx < 0 || idx >= playlist.length) return;
    const item = playlist[idx];
    resetCardUI(currentPlayBtn);
    currentPlayBtn = item.btn;
    currentAudioSrc = item.audio;
    currentTitleText = item.title;
    playlistIndex = idx;
    audioEl.src = item.audio;
    audioEl.play().catch(() => {
      const card = item.btn.closest('.episode-card');
      if (card) {
        const timeEl = card.querySelector('.progress-time');
        if (timeEl) timeEl.textContent = '\u97f3\u58f0\u30d5\u30a1\u30a4\u30eb\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093';
      }
      currentPlayBtn = null;
    });
    item.btn.classList.add('playing');
    updatePlayIcons(true);
    setMediaSession(item.title);
    const mt = getMiniEl('miniTitle');
    if (mt) mt.textContent = item.title;
    showMiniPlayer();
  }

  function bindPlayer(btn, audioSrc, title) {
    btn.addEventListener('click', () => {
      const card = btn.closest('.episode-card');
      const timeEl = card ? card.querySelector('.progress-time') : null;
      if (currentPlayBtn === btn) {
        if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
        else { audioEl.pause(); updatePlayIcons(false); }
        return;
      }
      resetCardUI(currentPlayBtn);
      audioEl.pause();
      audioEl.currentTime = 0;
      if (!audioSrc) { if (timeEl) timeEl.textContent = '\u97f3\u58f0\u30d5\u30a1\u30a4\u30eb\u672a\u8a2d\u5b9a'; return; }
      const idx = playlist.findIndex(p => p.btn === btn);
      playlistIndex = idx >= 0 ? idx : -1;
      currentPlayBtn = btn;
      currentAudioSrc = audioSrc;
      currentTitleText = title;
      audioEl.src = audioSrc;
      audioEl.play().catch(() => { if (timeEl) timeEl.textContent = '\u97f3\u58f0\u30d5\u30a1\u30a4\u30eb\u3092\u8aad\u307f\u8fbc\u3081\u307e\u305b\u3093'; currentPlayBtn = null; });
      btn.classList.add('playing');
      updatePlayIcons(true);
      setMediaSession(title);
      const mt = getMiniEl('miniTitle');
      if (mt) mt.textContent = title;
      showMiniPlayer();
    });
  }

  function buildPlaylist() {
    playlist = [];
    const episodeList = document.getElementById('episodeList');
    if (!episodeList) return;
    episodeList.querySelectorAll('.play-btn').forEach(btn => {
      if (btn.closest('.episode-card').style.display !== 'none') {
        playlist.push({ btn, audio: btn.dataset.audio || '', title: btn.dataset.title || '' });
      }
    });
  }

  // Audio time update
  // Normalize audio path to filename only for comparison
  function audioFileName(src) {
    if (!src) return '';
    return src.split('/').pop().split('?')[0];
  }

  audioEl.addEventListener('timeupdate', () => {
    if (!audioEl.duration) return;
    const pct = (audioEl.currentTime / audioEl.duration * 100) + '%';
    const timeStr = formatTime(audioEl.currentTime) + ' / ' + formatTime(audioEl.duration);
    // Mini player
    const mpf = getMiniEl('miniProgressFill');
    const mtime = getMiniEl('miniTime');
    if (mpf) mpf.style.width = pct;
    if (mtime) mtime.textContent = timeStr;
    // Episode card on home/all-episodes page
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      if (card) {
        const fill = card.querySelector('.progress-fill');
        const timeEl = card.querySelector('.progress-time');
        if (fill) fill.style.width = pct;
        if (timeEl) timeEl.textContent = timeStr;
      }
    }
    // Article page player (always check, regardless of currentPlayBtn)
    const artFill = document.getElementById('articleProgressFill');
    const artTime = document.getElementById('articleProgressTime');
    if (artFill || artTime) {
      const artBtn = document.getElementById('articlePlayBtn');
      if (artBtn && audioFileName(artBtn.dataset.audio) === audioFileName(currentAudioSrc)) {
        if (artFill) artFill.style.width = pct;
        if (artTime) artTime.textContent = timeStr;
      }
    }
    // All play buttons with matching audio (covers home cards after SPA navigation)
    if (currentAudioSrc) {
      document.querySelectorAll('.play-btn[data-audio]').forEach(function(btn) {
        if (btn === currentPlayBtn) return;
        if (audioFileName(btn.dataset.audio) === audioFileName(currentAudioSrc)) {
          var card = btn.closest('.episode-card');
          if (card) {
            var fill = card.querySelector('.progress-fill');
            var tEl = card.querySelector('.progress-time');
            if (fill) fill.style.width = pct;
            if (tEl) tEl.textContent = timeStr;
          }
        }
      });
    }
    if ('mediaSession' in navigator && navigator.mediaSession.setPositionState) {
      try { navigator.mediaSession.setPositionState({ duration: audioEl.duration, playbackRate: audioEl.playbackRate, position: audioEl.currentTime }); } catch(e) {}
    }
  });

  // Auto-play next
  audioEl.addEventListener('ended', () => {
    resetCardUI(currentPlayBtn);
    currentPlayBtn = null;
    updatePlayIcons(false);
    const nextIdx = playlistIndex + 1;
    if (nextIdx < playlist.length) playFromPlaylist(nextIdx);
    else { playlistIndex = -1; hideMiniPlayer(); }
  });

  // Bind mini player controls (re-bind after each navigation since DOM may change)
  function bindMiniPlayer() {
    const mpb = getMiniEl('miniPlayBtn');
    const mcb = getMiniEl('miniCloseBtn');
    const mpbar = getMiniEl('miniProgressBar');

    if (mpb) {
      // Remove old listeners by cloning
      const newMpb = mpb.cloneNode(true);
      mpb.parentNode.replaceChild(newMpb, mpb);
      newMpb.addEventListener('click', () => {
        if (!audioEl.src) return;
        if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
        else { audioEl.pause(); updatePlayIcons(false); }
      });
    }
    if (mcb) {
      const newMcb = mcb.cloneNode(true);
      mcb.parentNode.replaceChild(newMcb, mcb);
      newMcb.addEventListener('click', stopCurrent);
    }
    if (mpbar) {
      const newMpbar = mpbar.cloneNode(true);
      mpbar.parentNode.replaceChild(newMpbar, mpbar);
      newMpbar.addEventListener('click', (e) => {
        if (!audioEl.duration) return;
        const rect = newMpbar.getBoundingClientRect();
        audioEl.currentTime = ((e.clientX - rect.left) / rect.width) * audioEl.duration;
      });
    }

    // Restore mini player state if audio is playing
    if (currentAudioSrc && audioEl.src) {
      const mt = getMiniEl('miniTitle');
      if (mt) mt.textContent = currentTitleText;
      if (!audioEl.paused) {
        showMiniPlayer();
        updatePlayIcons(true);
      } else if (audioEl.currentTime > 0) {
        showMiniPlayer();
        updatePlayIcons(false);
      }
    }
  }

  // =========================================================
  //  SPA ROUTER
  // =========================================================

  // Internal pages that participate in SPA routing
  // Non-SPA file extensions (let browser handle these)
  const NON_SPA_EXT = ['.mp3', '.wav', '.ogg', '.mp4', '.pdf', '.zip', '.xml', '.json', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico'];

  function isSPALink(anchor) {
    // Must be same origin
    try {
      const url = new URL(anchor.href, location.origin);
      if (url.origin !== location.origin) return false;
    } catch(e) { return false; }
    // Must not have target
    if (anchor.target && anchor.target !== '_self') return false;
    // Must not be a download
    if (anchor.hasAttribute('download')) return false;
    // Skip non-HTML files
    const pathname = new URL(anchor.href, location.origin).pathname;
    for (var i = 0; i < NON_SPA_EXT.length; i++) {
      if (pathname.toLowerCase().endsWith(NON_SPA_EXT[i])) return false;
    }
    // Must end in .html or be a directory path (no extension)
    var lastSegment = pathname.split('/').pop();
    if (lastSegment && lastSegment.indexOf('.') !== -1 && !lastSegment.endsWith('.html')) return false;
    return true;
  }

  // Parse fetched HTML and extract parts
  function parseHTML(html) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    return doc;
  }

  // Get the swappable content area from a document
  function getSwapContent(doc) {
    // We swap everything between </nav> and <div class="mini-player">
    // Strategy: get everything in body except nav, mini-player, and scripts
    const body = doc.body;
    const nav = body.querySelector('nav.navbar');
    const miniPlayer = body.querySelector('.mini-player');

    // Collect all nodes between nav and mini-player
    const contentNodes = [];
    let collecting = false;
    for (let node of body.childNodes) {
      if (node === nav) { collecting = true; continue; }
      if (node.nodeType === 1 && node.classList && node.classList.contains('mini-player')) { collecting = false; continue; }
      // Skip script tags at the bottom
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') continue;
      if (collecting) contentNodes.push(node.cloneNode(true));
    }
    return contentNodes;
  }

  // Get nav HTML from a parsed document
  function getNavContent(doc) {
    const nav = doc.body.querySelector('nav.navbar');
    return nav ? nav.innerHTML : null;
  }

  // Get page-specific styles from <head>
  function getPageStyles(doc) {
    const styles = doc.head.querySelectorAll('style');
    return Array.from(styles).map(s => s.outerHTML).join('\n');
  }

  // Extract meta/OG/canonical info from a parsed document
  function extractMeta(doc) {
    const get = (sel, attr) => {
      const el = doc.head.querySelector(sel);
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

  // Update or create a <meta> tag
  function setMeta(selector, attr, value) {
    if (value == null) return;
    let el = document.head.querySelector(selector);
    if (el) {
      el.setAttribute(attr, value);
    } else {
      el = document.createElement(selector.startsWith('link') ? 'link' : 'meta');
      // Parse selector to set attributes, e.g. meta[name="description"]
      const matches = selector.match(/\[(\w[\w-]*)="([^"]+)"\]/g);
      if (matches) {
        matches.forEach(m => {
          const [, k, v] = m.match(/\[(\w[\w-]*)="([^"]+)"\]/);
          el.setAttribute(k, v);
        });
      }
      el.setAttribute(attr, value);
      document.head.appendChild(el);
    }
  }

  // Apply meta tags from extracted info
  function applyMeta(meta) {
    if (!meta) return;
    setMeta('meta[name="description"]',        'content', meta.description);
    setMeta('meta[property="og:title"]',       'content', meta.ogTitle);
    setMeta('meta[property="og:description"]', 'content', meta.ogDescription);
    setMeta('meta[property="og:url"]',         'content', meta.ogUrl);
    setMeta('link[rel="canonical"]',           'href',    meta.canonical);
  }

  // Apply swap
  function applySwap(contentNodes, pageStyles, title, navHTML, meta) {
    // Update title
    document.title = title;

    // Update meta / OG / canonical tags
    applyMeta(meta);

    // Remove existing page-specific styles
    document.querySelectorAll('style[data-spa-page]').forEach(s => s.remove());

    // Add new page styles
    if (pageStyles) {
      const styleContainer = document.createElement('div');
      styleContainer.innerHTML = pageStyles;
      Array.from(styleContainer.children).forEach(s => {
        s.setAttribute('data-spa-page', 'true');
        document.head.appendChild(s);
      });
    }

    // Update nav content (links change between index and sub-pages)
    if (navHTML) {
      const nav = document.querySelector('nav.navbar');
      if (nav) nav.innerHTML = navHTML;
    }

    // Find the swap container
    const spaContent = document.getElementById('spaContent');
    if (spaContent) {
      spaContent.innerHTML = '';
      contentNodes.forEach(node => spaContent.appendChild(node));
    }
  }

  // After content is swapped, re-initialize page-specific behaviors
  function reinitPage() {
    // Hamburger menu
    const hamburger = document.getElementById('hamburger');
    const navLinks = document.getElementById('navLinks');
    if (hamburger && navLinks) {
      const newHamburger = hamburger.cloneNode(true);
      hamburger.parentNode.replaceChild(newHamburger, hamburger);
      newHamburger.addEventListener('click', () => navLinks.classList.toggle('active'));
      navLinks.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => navLinks.classList.remove('active'));
      });
    }

    // Bind mini player controls
    bindMiniPlayer();

    // Smooth scroll for hash links
    document.querySelectorAll('a[href^="#"]').forEach(a => {
      a.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href === '#' || href === '') return;
        const t = document.querySelector(href);
        if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth' }); }
      });
    });

    // FAQ
    document.querySelectorAll('.faq-item').forEach(item => {
      const q = item.querySelector('.faq-question');
      if (q) {
        q.addEventListener('click', () => {
          const wasActive = item.classList.contains('active');
          document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('active'));
          if (!wasActive) item.classList.add('active');
        });
      }
    });

    // SNS Coming Soon
    document.querySelectorAll('.sns-coming-soon').forEach(a => {
      a.addEventListener('click', e => {
        e.preventDefault();
        const toast = document.createElement('div');
        toast.textContent = 'SNS\u30a2\u30ab\u30a6\u30f3\u30c8\u306f\u6e96\u5099\u4e2d\u3067\u3059';
        toast.style.cssText = 'position:fixed;bottom:32px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:12px 24px;border-radius:8px;font-size:14px;z-index:9999;opacity:0;transition:opacity .3s';
        document.body.appendChild(toast);
        requestAnimationFrame(() => toast.style.opacity = '1');
        setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
      });
    });

    // Stat counter — skip here, animation triggered after fetch updates count

    // Floating formulas (index page)
    initFloatingFormulas();

    // Navbar scroll behavior
    const navbar = document.getElementById('navbar');
    if (navbar) {
      // On non-index pages, keep scrolled class
      const isIndex = location.pathname.endsWith('index.html') || location.pathname.endsWith('/') || location.pathname === '';
      if (!isIndex) {
        navbar.classList.add('scrolled');
      } else {
        navbar.classList.toggle('scrolled', window.scrollY > 20);
      }
    }

    // Reveal animations
    initReveal();

    // Modal (index page)
    initModal();

    // Request form (index page)
    initRequestForm();

    // Popular tags (index page)
    initPopularTags();

    // Episode loading (index page)
    initIndexEpisodes();

    // All-episodes page
    initAllEpisodesPage();

    // Contact form
    initContactForm();

    // Article page player (episodes/ep00X.html)
    initArticlePlayer();

    // Re-init SPA link interception on new content
    interceptLinks();

    // Try to re-associate current playing button with new DOM
    reassociatePlayingButton();

    // Scroll to top (unless there's a hash)
    if (!location.hash) {
      window.scrollTo(0, 0);
    } else {
      const target = document.querySelector(location.hash);
      if (target) {
        setTimeout(() => target.scrollIntoView({ behavior: 'smooth' }), 100);
      }
    }

    // Try to push AdSense ads (they may not work perfectly with SPA)
    try {
      const adSlots = document.querySelectorAll('.adsbygoogle');
      adSlots.forEach(ad => {
        if (!ad.getAttribute('data-ad-status')) {
          try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch(e) {}
        }
      });
    } catch(e) {}
  }

  // After SPA navigation, try to find the play button matching current audio
  function reassociatePlayingButton() {
    // Reset ALL play buttons to default state first
    document.querySelectorAll('.play-btn').forEach(function(btn) {
      btn.classList.remove('playing');
      btn.innerHTML = '<span class="play-icon">&#9654;</span>';
      var card = btn.closest('.episode-card');
      if (card) {
        var fill = card.querySelector('.progress-fill');
        var timeEl = card.querySelector('.progress-time');
        if (fill) fill.style.width = '0%';
      }
    });

    if (!currentAudioSrc || (audioEl.paused && audioEl.currentTime === 0)) return;
    // Find button with matching data-audio and restore its playing state
    var btns = document.querySelectorAll('.play-btn[data-audio]');
    var found = false;
    btns.forEach(function(btn) {
      if (audioFileName(btn.dataset.audio) === audioFileName(currentAudioSrc)) {
        currentPlayBtn = btn;
        btn.classList.add('playing');
        updatePlayIcons(!audioEl.paused);
        // Update progress UI
        var card = btn.closest('.episode-card');
        if (card && audioEl.duration) {
          var fill = card.querySelector('.progress-fill');
          var timeEl = card.querySelector('.progress-time');
          var pct = (audioEl.currentTime / audioEl.duration * 100) + '%';
          if (fill) fill.style.width = pct;
          if (timeEl) timeEl.textContent = formatTime(audioEl.currentTime) + ' / ' + formatTime(audioEl.duration);
        }
        found = true;
      }
    });
    if (!found) {
      // Current page doesn't have that episode - clear card reference but keep playing
      currentPlayBtn = null;
    }
    // Rebuild playlist
    buildPlaylist();
    // Update playlist index
    if (currentPlayBtn) {
      const idx = playlist.findIndex(p => p.btn === currentPlayBtn);
      playlistIndex = idx >= 0 ? idx : -1;
    }
  }

  function initFloatingFormulas() {
    const container = document.querySelector('.hero-formulas');
    if (!container) return;
    const items = container.querySelectorAll('.formula');
    const w = window.innerWidth;
    const scale = Math.min(Math.max(w / 1200, 0.45), 1);
    const minSize = Math.round(16 * scale);
    const maxSize = Math.round(26 * scale);
    const state = [];
    items.forEach((el) => {
      const size = minSize + Math.random() * (maxSize - minSize);
      const x = 5 + Math.random() * 90;
      const y = 5 + Math.random() * 90;
      const rot = -15 + Math.random() * 30;
      const vx = (0.3 + Math.random() * 0.7) * (Math.random() < 0.5 ? 1 : -1);
      const vy = (0.2 + Math.random() * 0.5) * (Math.random() < 0.5 ? 1 : -1);
      el.style.left = x + '%';
      el.style.top = y + '%';
      el.style.fontSize = Math.round(size) + 'px';
      el.style.transform = 'rotate(' + rot.toFixed(1) + 'deg)';
      el.style.opacity = '1';
      state.push({ el, x, y, vx, vy, rot });
    });
    // Cancel previous animation if any
    if (window._formulaAnimId) cancelAnimationFrame(window._formulaAnimId);
    let last = performance.now();
    function tick(now) {
      const dt = (now - last) / 1000;
      last = now;
      for (const s of state) {
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
    const els = document.querySelectorAll(
      '.episode-card,.service-card,.step-card,.pricing-card,.testimonial-card,.faq-item,.request-form-card,.request-info-card'
    );
    if (!els.length) return;
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
      el.style.transition = 'opacity 0.4s ease ' + ((i % 3) * 0.06) + 's, transform 0.4s ease ' + ((i % 3) * 0.06) + 's';
      obs.observe(el);
    });
  }

  function initModal() {
    const modal = document.getElementById('signupModal');
    if (!modal) return;
    const modalTitle = document.getElementById('modalTitle');
    const modalDesc = document.getElementById('modalDesc');
    const modalClose = document.getElementById('modalClose');
    let currentPlan = null;

    function openModal(title, desc) {
      if (modalTitle) modalTitle.textContent = title || '\u7121\u6599\u3067\u59cb\u3081\u308b';
      if (modalDesc) modalDesc.textContent = desc || '\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u3067\u7c21\u5358\u767b\u9332';
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
    function closeModal() {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
    if (modalClose) modalClose.addEventListener('click', closeModal);
    modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

    document.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        const msgs = {
          'signup-free': ['\u7121\u6599\u3067\u59cb\u3081\u308b', '\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u3067\u7c21\u5358\u767b\u9332\u3002', 'free'],
          'contact': ['\u304a\u554f\u3044\u5408\u308f\u305b', '\u3054\u8cea\u554f\u30fb\u3054\u76f8\u8ac7\u306f\u3053\u3061\u3089\u304b\u3089\u3002', null]
        };
        const m = msgs[btn.dataset.action];
        if (m) { currentPlan = m[2]; openModal(m[0], m[1]); }
      });
    });

    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
      signupForm.addEventListener('submit', e => {
        e.preventDefault();
        const emailVal = document.getElementById('email').value;
        const btn = e.target.querySelector('button[type="submit"]');
        btn.textContent = '\u767b\u9332\u4e2d...';
        btn.disabled = true;
        const planName = currentPlan || 'free';
        fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ email: emailVal, plan: planName, _subject: 'DeepCast AI \u65b0\u898f\u4f1a\u54e1\u767b\u9332 (' + planName + ')', _captcha: 'false' })
        })
        .then(r => r.json())
        .then(() => {
          localStorage.setItem('deepcast_member', JSON.stringify({ email: emailVal, plan: planName, registered: new Date().toISOString() }));
          e.target.innerHTML = '<div style="text-align:center;padding:24px 0"><div style="font-size:24px;margin-bottom:8px">&#10003;</div><h3 style="font-size:17px;font-weight:600;margin-bottom:4px">\u767b\u9332\u5b8c\u4e86</h3><p style="color:var(--text-secondary);font-size:13px">' + emailVal + ' \u3067\u767b\u9332\u3057\u307e\u3057\u305f\u3002</p></div>';
          setTimeout(closeModal, 3000);
        })
        .catch(() => {
          btn.textContent = '\u767b\u9332\u306b\u5931\u6557\u3057\u307e\u3057\u305f';
          setTimeout(() => { btn.textContent = '\u7121\u6599\u3067\u767b\u9332\u3059\u308b'; btn.disabled = false; }, 2000);
        });
      });
    }
  }

  function initRequestForm() {
    const reqForm = document.getElementById('requestForm');
    if (!reqForm) return;
    reqForm.addEventListener('submit', e => {
      e.preventDefault();
      const data = new FormData(reqForm);
      const body = {
        topic: data.get('topic'), category: data.get('category'), depth: data.get('depth'),
        detail: data.get('detail'), email: data.get('email'),
        _subject: 'DeepCast AI \u65b0\u898f\u30ea\u30af\u30a8\u30b9\u30c8', _captcha: 'false'
      };
      const btn = reqForm.querySelector('button[type="submit"]');
      const origText = btn.textContent;
      btn.textContent = '\u9001\u4fe1\u4e2d...';
      btn.disabled = true;
      fetch('https://formsubmit.co/ajax/2525nxrei@gmail.com', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(body)
      })
      .then(r => r.json())
      .then(() => {
        btn.textContent = '\u53d7\u4ed8\u5b8c\u4e86!';
        btn.style.background = '#3a8a44';
        setTimeout(() => { reqForm.reset(); btn.textContent = origText; btn.style.background = ''; btn.disabled = false; }, 3000);
      })
      .catch(() => {
        btn.textContent = '\u9001\u4fe1\u306b\u5931\u6557\u3057\u307e\u3057\u305f';
        setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 2000);
      });
    });
  }

  function initPopularTags() {
    document.querySelectorAll('.popular-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        const f = document.getElementById('requestTopic');
        if (f) { f.value = tag.dataset.topic; f.focus(); f.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    });
  }

  // =========================================================
  //  AUTO CATEGORY DETECTION
  //  Analyzes title, description, and tags to assign category
  // =========================================================
  const CATEGORY_KEYWORDS = {
    tech: [
      'AI', 'GPT', 'Gemini', 'LLM', '機械学習', 'ディープラーニング', '深層学習',
      'プログラミング', 'アルゴリズム', 'ブロックチェーン', 'Web3', '半導体', 'チップ',
      '量子コンピュータ', 'サイバー', 'ハッキング', 'プラットフォーム', 'クラウド',
      'ロボット', '自動運転', 'VR', 'AR', 'メタバース', '5G', '6G', 'IoT',
      'スマートフォン', 'アプリ', 'ソフトウェア', 'ハードウェア', 'API',
      'オープンソース', 'テクノロジー', '技術', 'デジタル', 'ネットワーク',
      '暗号化', 'セキュリティ', 'データ', 'サーバー', '通信', 'インターネット',
      'Google', 'OpenAI', 'Apple', 'Microsoft', 'Meta', 'NVIDIA',
      '地政学', '監視', 'GAFAM', '海底ケーブル', 'TSMC', 'AGI'
    ],
    business: [
      '経済', 'ビジネス', '投資', '株', '資産', '金融', '起業', 'スタートアップ',
      'マーケティング', '経営', '利益', '市場', 'GDP', 'インフレ', 'デフレ',
      '円安', '円高', '為替', '貿易', 'サブスク', '年収', '所得', '給料',
      '不動産', 'ローン', '保険', '年金', '税金', '節税', '副業', '転職',
      'リモートワーク', 'フリーランス', '成功', 'キャリア', '貯金', '貯蓄',
      '消費', '購買', 'マネー', 'ファイナンス', '資本主義', '格差',
      'ベーシックインカム', '失業', '労働', 'ビットコイン', '暗号資産',
      '宝くじ', 'MMT', '通貨', '貨幣', '推し活', 'DAO', 'Web3',
      '老後', '2000万', '貧困', '中間層', '富裕層'
    ],
    science: [
      '科学', 'サイエンス', '物理', '化学', '生物', '数学', '医学', '医療',
      '遺伝子', 'DNA', 'ゲノム', '進化', '宇宙', '天文', '量子', '素粒子',
      '相対性理論', '脳', '神経', 'ニューロン', '認知', '心理学', '実験',
      '研究', '論文', '仮説', '臨床', '細胞', 'ウイルス', '免疫',
      'バイオ', 'テクノロジー', 'エネルギー', '核融合', '気候変動', '環境',
      '生態系', '絶滅', '火星', 'ブラックホール', '暗黒物質', 'フェルミ',
      '脳科学', '神経美学', 'ドーパミン', 'セロトニン', '依存', '中毒',
      '睡眠', '記憶', '知能', 'IQ', '老化', 'テロメア', 'CRISPR',
      '意識', '哲学ゾンビ', '多世界解釈', '生命'
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
      'アイデンティティ', '意味', '死', '不死', '正義', '功利主義'
    ]
  };

  function autoDetectCategory(ep) {
    var text = (ep.title || '') + ' ' + (ep.description || '') + ' ' + (ep.tags || []).join(' ');
    text = text.toLowerCase();
    var scores = { tech: 0, business: 0, science: 0, society: 0 };
    for (var cat in CATEGORY_KEYWORDS) {
      CATEGORY_KEYWORDS[cat].forEach(function(kw) {
        if (text.indexOf(kw.toLowerCase()) !== -1) {
          scores[cat]++;
        }
      });
    }
    var best = 'society';
    var bestScore = 0;
    for (var c in scores) {
      if (scores[c] > bestScore) {
        bestScore = scores[c];
        best = c;
      }
    }
    return best;
  }

  function autoAssignCategories(episodes) {
    episodes.forEach(function(ep) {
      ep.category = autoDetectCategory(ep);
    });
    return episodes;
  }

  // Category label map
  var CATEGORY_LABELS = {
    tech: 'テクノロジー',
    business: 'ビジネス',
    science: 'サイエンス',
    society: '社会・文化'
  };

  // Dynamically create filter buttons from existing categories
  function buildFilterButtons(container, episodes) {
    var cats = {};
    episodes.forEach(function(ep) {
      if (ep.category) cats[ep.category] = true;
    });
    // Always show "all" first
    var html = '<button class="filter-btn active" data-filter="all">すべて</button>';
    // Ordered categories
    ['tech', 'business', 'science', 'society'].forEach(function(cat) {
      if (cats[cat]) {
        html += '<button class="filter-btn" data-filter="' + cat + '">' + (CATEGORY_LABELS[cat] || cat) + '</button>';
      }
    });
    container.innerHTML = html;
  }

  // Stat counter animation (called after episode count is known)
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

  // Episode rendering shared between index and all-episodes
  function renderEpisode(ep) {
    var categoryLabel = CATEGORY_LABELS[ep.category] || ep.category || '';
    const tags = ep.tags.map(t => '<span class="tag">' + t + '</span>').join('');
    return '<article class="episode-card" data-category="' + ep.category + '">' +
      '<div class="episode-header">' +
        '<div class="episode-info">' +
          '<span class="episode-badge category-' + ep.category + '">' + (CATEGORY_LABELS[ep.category] || '') + '</span>' +
          '<span class="episode-number">#' + ep.id + '</span>' +
          '<span class="episode-date">' + ep.date + '</span>' +
          '<span class="episode-duration">' + ep.duration + '</span>' +
        '</div>' +
        '<h3 class="episode-title">' + ep.title + '</h3>' +
        '<p class="episode-desc">' + ep.description + '</p>' +
        '<div class="episode-tags">' + tags + '</div>' +
      '</div>' +
      '<div class="episode-embed">' +
        '<div class="episode-player">' +
          '<button class="play-btn" data-audio="' + (ep.audio || '') + '" data-title="' + ep.title + '" aria-label="\u518d\u751f">' +
            '<span class="play-icon">&#9654;</span>' +
          '</button>' +
          '<div class="episode-progress">' +
            '<div class="progress-bar"><div class="progress-fill" style="width:0%"></div></div>' +
            '<span class="progress-time">0:00 / ' + ep.duration + '</span>' +
          '</div>' +
        '</div>' +
        (ep.article ? '<a href="' + ep.article + '" class="read-article-btn">\u8981\u7d04\u3092\u8aad\u3080 &rarr;</a>' : '') +
      '</div>' +
    '</article>';
  }

  function initIndexEpisodes() {
    const episodeList = document.getElementById('episodeList');
    if (!episodeList) return;
    // Only run on index page (index has filters but no search bar)
    if (document.getElementById('episodeSearch')) return; // all-episodes page

    fetch('episodes/episodes.json')
      .then(r => r.json())
      .then(episodes => {
        if (!episodes.length) {
          episodeList.innerHTML = '<p class="loading-text">\u30a8\u30d4\u30bd\u30fc\u30c9\u306f\u307e\u3060\u3042\u308a\u307e\u305b\u3093\u3002</p>';
          return;
        }
        // Auto-detect categories from content
        autoAssignCategories(episodes);
        // Build filter buttons dynamically based on existing categories
        var filterContainer = document.querySelector('.episode-filters');
        if (filterContainer) buildFilterButtons(filterContainer, episodes);

        episodeList.innerHTML = episodes.map(renderEpisode).join('');
        // Update episode count stat dynamically and trigger animation
        document.querySelectorAll('.stat-number[data-count]').forEach(el => {
          el.dataset.count = episodes.length;
          animateCounter(el);
        });
        episodeList.querySelectorAll('.play-btn').forEach(btn => {
          bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
        });
        // Filters
        const btns = document.querySelectorAll('.filter-btn');
        const cards = document.querySelectorAll('.episode-card');
        btns.forEach(btn => {
          btn.addEventListener('click', () => {
            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            cards.forEach(c => {
              c.style.display = (btn.dataset.filter === 'all' || c.dataset.category === btn.dataset.filter) ? '' : 'none';
            });
            buildPlaylist();
          });
        });
        buildPlaylist();
        initReveal();
        reassociatePlayingButton();
      })
      .catch(() => {
        const fallback = [
          { id: 3, title: "GPT-5 vs Gemini 2.5\uff1a\u6b21\u4e16\u4ee3AI\u306e\u8987\u6a29\u4e89\u3044", description: "OpenAI\u3068Google\u306e\u6700\u65b0\u30e2\u30c7\u30eb\u6bd4\u8f03\u3002", date: "2026.03.02", category: "tech", tags: ["AI", "\u30c6\u30af\u30ce\u30ed\u30b8\u30fc"], duration: "5:12", free: true, audio: "" },
          { id: 2, title: "\u30b9\u30bf\u30fc\u30c8\u30a2\u30c3\u30d7\u8cc7\u91d1\u8abf\u9054\u306e\u65b0\u5e38\u8b58 2026", description: "VC\u5e02\u5834\u306e\u5909\u5316\u3001AI\u30b9\u30bf\u30fc\u30c8\u30a2\u30c3\u30d7\u3078\u306e\u6295\u8cc7\u30c8\u30ec\u30f3\u30c9\u3002", date: "2026.03.01", category: "business", tags: ["\u30d3\u30b8\u30cd\u30b9"], duration: "4:58", free: true, audio: "" },
          { id: 1, title: "\u91cf\u5b50\u30b3\u30f3\u30d4\u30e5\u30fc\u30bf\u306e\u5b9f\u7528\u5316\u304c\u898b\u3048\u3066\u304d\u305f", description: "IBM\u3068Google\u306e\u91cf\u5b50\u8d85\u8d8a\u6027\u7af6\u4e89\u3002\u5b9f\u7528\u5316\u306e\u30e6\u30fc\u30b9\u30b1\u30fc\u30b9\u3002", date: "2026.02.28", category: "science", tags: ["\u30b5\u30a4\u30a8\u30f3\u30b9"], duration: "5:31", free: false, audio: "" }
        ];
        episodeList.innerHTML = fallback.map(renderEpisode).join('');
        episodeList.querySelectorAll('.play-btn').forEach(btn => {
          bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
        });
        buildPlaylist();
        initReveal();
      });
  }

  function initAllEpisodesPage() {
    const episodeSearch = document.getElementById('episodeSearch');
    if (!episodeSearch) return;
    const episodeList = document.getElementById('episodeList');
    const episodeCount = document.getElementById('episodeCount');
    const noResults = document.getElementById('noResults');
    if (!episodeList) return;

    let allEpisodes = [];
    let activeFilter = 'all';

    function displayEpisodes(episodes) {
      if (!episodes.length) {
        episodeList.innerHTML = '';
        if (noResults) noResults.style.display = 'block';
        if (episodeCount) episodeCount.textContent = '';
        return;
      }
      if (noResults) noResults.style.display = 'none';
      episodeList.innerHTML = episodes.map(renderEpisode).join('');
      if (episodeCount) episodeCount.textContent = episodes.length + '\u4ef6\u306e\u30a8\u30d4\u30bd\u30fc\u30c9';
      episodeList.querySelectorAll('.play-btn').forEach(btn => {
        bindPlayer(btn, btn.dataset.audio, btn.dataset.title);
      });
      buildPlaylist();
      reassociatePlayingButton();
    }

    function applyFilters() {
      const query = episodeSearch.value.toLowerCase();
      const filtered = allEpisodes.filter(ep => {
        const matchCategory = activeFilter === 'all' || ep.category === activeFilter;
        const matchSearch = !query ||
          ep.title.toLowerCase().includes(query) ||
          ep.description.toLowerCase().includes(query) ||
          ep.tags.some(t => t.toLowerCase().includes(query));
        return matchCategory && matchSearch;
      });
      displayEpisodes(filtered);
    }

    fetch('episodes/episodes.json')
      .then(r => r.json())
      .then(episodes => {
        // Auto-detect categories from content
        autoAssignCategories(episodes);
        // Build filter buttons dynamically
        var filterContainer = document.querySelector('.episode-filters');
        if (filterContainer) {
          buildFilterButtons(filterContainer, episodes);
          // Re-bind filter button events after dynamic generation
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
      .catch(() => {
        episodeList.innerHTML = '<p class="loading-text">\u30a8\u30d4\u30bd\u30fc\u30c9\u306e\u8aad\u307f\u8fbc\u307f\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002</p>';
      });

    episodeSearch.addEventListener('input', applyFilters);
  }

  function initArticlePlayer() {
    var btn = document.getElementById('articlePlayBtn');
    if (!btn) return;
    var audioSrc = btn.dataset.audio;
    var title = btn.dataset.title;
    if (!audioSrc) return;
    bindPlayer(btn, audioSrc, title);
  }

  function initContactForm() {
    const form = document.querySelector('.contact-form');
    if (!form) return;
    // The contact form uses traditional form submission (action="https://formspree.io/...")
    // We need to handle it specially for SPA - prevent default and use fetch
    if (form.getAttribute('action') && form.getAttribute('method') === 'POST') {
      form.addEventListener('submit', function(e) {
        e.preventDefault();
        const data = new FormData(form);
        const btn = form.querySelector('.form-submit') || form.querySelector('button[type="submit"]');
        const origText = btn ? btn.textContent : '';
        if (btn) { btn.textContent = '\u9001\u4fe1\u4e2d...'; btn.disabled = true; }

        fetch(form.action, {
          method: 'POST',
          body: data,
          headers: { 'Accept': 'application/json' }
        })
        .then(r => {
          if (r.ok) {
            form.innerHTML = '<div style="text-align:center;padding:48px 0"><div style="font-size:32px;margin-bottom:12px">&#10003;</div><h3 style="font-size:18px;font-weight:600;margin-bottom:8px">\u9001\u4fe1\u5b8c\u4e86</h3><p style="color:var(--text-secondary);font-size:14px">\u304a\u554f\u3044\u5408\u308f\u305b\u3042\u308a\u304c\u3068\u3046\u3054\u3056\u3044\u307e\u3059\u3002<br>\u901a\u5e382\u55b6\u696d\u65e5\u4ee5\u5185\u306b\u3054\u8fd4\u4fe1\u3044\u305f\u3057\u307e\u3059\u3002</p></div>';
          } else {
            throw new Error('Failed');
          }
        })
        .catch(() => {
          if (btn) {
            btn.textContent = '\u9001\u4fe1\u306b\u5931\u6557\u3057\u307e\u3057\u305f';
            setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 2000);
          }
        });
      });
    }
  }

  // =========================================================
  //  SPA NAVIGATION
  // =========================================================

  let isNavigating = false;

  function navigateTo(url, pushState) {
    if (isNavigating) return;
    isNavigating = true;

    // Show a subtle loading indicator
    document.body.style.opacity = '0.7';
    document.body.style.transition = 'opacity 0.15s';

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(html => {
        const doc = parseHTML(html);
        const contentNodes = getSwapContent(doc);
        const pageStyles = getPageStyles(doc);
        const title = doc.title;
        const navHTML = getNavContent(doc);
        const meta = extractMeta(doc);

        applySwap(contentNodes, pageStyles, title, navHTML, meta);

        if (pushState !== false) {
          history.pushState({ spa: true }, title, url);
        }

        // Restore opacity
        document.body.style.opacity = '1';
        isNavigating = false;

        reinitPage();
      })
      .catch(err => {
        console.warn('SPA navigation failed, falling back to full page load:', err);
        document.body.style.opacity = '1';
        isNavigating = false;
        // Fallback: do a full page load
        location.href = url;
      });
  }

  function interceptLinks() {
    // Use event delegation on the document for all clicks
    // This is set up once below. This function is a no-op placeholder
    // since we use event delegation.
  }

  // Global click handler for SPA link interception
  document.addEventListener('click', function(e) {
    // Find closest anchor
    const anchor = e.target.closest('a');
    if (!anchor) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.defaultPrevented) return;

    // Check if it's a hash-only link on the current page
    const href = anchor.getAttribute('href');
    if (!href) return;

    // Handle hash links to other pages (e.g., "index.html#episodes")
    if (href.includes('#') && !href.startsWith('#')) {
      const hashPart = href.split('#')[1];
      try {
        const linkUrl = new URL(href, location.href);
        // If same page, just scroll
        if (linkUrl.pathname === location.pathname) {
          e.preventDefault();
          const target = document.getElementById(hashPart);
          if (target) target.scrollIntoView({ behavior: 'smooth' });
          return;
        }
      } catch(ex) {}
    }

    // Skip pure hash links
    if (href.startsWith('#')) return;

    // Check if it's an SPA-eligible link
    if (!isSPALink(anchor)) return;

    try {
      const linkUrl = new URL(href, location.href);
      if (linkUrl.origin !== location.origin) return;

      e.preventDefault();
      navigateTo(linkUrl.href, true);
    } catch(ex) {
      // Not a valid URL, let browser handle it
    }
  });

  // Handle browser back/forward
  window.addEventListener('popstate', function(e) {
    navigateTo(location.href, false);
  });

  // Scroll-based navbar
  window.addEventListener('scroll', function() {
    const navbar = document.getElementById('navbar');
    if (!navbar) return;
    const isIndex = location.pathname.endsWith('index.html') || location.pathname.endsWith('/') || location.pathname === '';
    if (isIndex) {
      navbar.classList.toggle('scrolled', window.scrollY > 20);
    }
  });

  // =========================================================
  //  INITIAL PAGE SETUP
  // =========================================================

  // Wrap initial page content for SPA swapping
  function setupInitialPage() {
    // If spaContent wrapper doesn't exist yet, create it
    if (document.getElementById('spaContent')) {
      // Already set up
      bindMiniPlayer();
      reinitPage();
      return;
    }

    const body = document.body;
    const nav = body.querySelector('nav.navbar');
    const miniPlayer = body.querySelector('.mini-player');

    if (!nav || !miniPlayer) {
      // Can't set up SPA - page structure not compatible
      bindMiniPlayer();
      return;
    }

    // Create wrapper for swappable content
    const wrapper = document.createElement('div');
    wrapper.id = 'spaContent';

    // Move all nodes between nav and mini-player into wrapper
    const nodesToMove = [];
    let collecting = false;
    for (let i = 0; i < body.childNodes.length; i++) {
      const node = body.childNodes[i];
      if (node === nav) { collecting = true; continue; }
      if (node === miniPlayer) { collecting = false; continue; }
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') continue;
      if (collecting) nodesToMove.push(node);
    }

    // Insert wrapper after nav
    nav.insertAdjacentElement('afterend', wrapper);
    nodesToMove.forEach(node => wrapper.appendChild(node));

    bindMiniPlayer();
    // Initialize all page-specific behaviors
    reinitPage();
  }

  // Run setup when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupInitialPage);
  } else {
    setupInitialPage();
  }

})();
