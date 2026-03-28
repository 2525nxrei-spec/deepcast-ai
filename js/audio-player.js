// ===================================================================
//  DeepCast AI - Audio Player (persistent across SPA navigations)
//  オーディオ再生、プレイリスト、MediaSession、ミニプレイヤー管理
// ===================================================================

(function () {
  'use strict';

  const audioEl = new Audio();
  audioEl.preload = 'metadata';
  // エピソード再生時間の上限（2分30秒 = 150秒）
  const MAX_DURATION_SEC = 150;

  let currentPlayBtn = null;
  let currentAudioSrc = '';
  let currentTitleText = '';
  let playlist = [];
  let playlistIndex = -1;
  // オーディオファイル名 → 記事URLのマッピング（再生終了後の自動遷移用）
  let audioToArticle = {};

  // ファイル名のみ取得（パス比較用）
  function audioFileName(src) {
    if (!src) return '';
    return src.split('/').pop().split('?')[0];
  }

  // 認証付き音声URL取得（API経由のPro音声対応）
  // /api/audio/xxx 形式のURLならJWT付きfetchでBlob URLを作成
  function resolveAudioSrc(src) {
    if (!src) return Promise.resolve('');
    // API経由のURLかチェック
    if (src.indexOf('/api/audio/') === -1) {
      return Promise.resolve(src);
    }
    // JWTトークンを取得
    var token = (typeof DEEPCAST_AUTH !== 'undefined' && DEEPCAST_AUTH.getToken) ? DEEPCAST_AUTH.getToken() : null;
    var headers = {};
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return fetch(src, { headers: headers })
      .then(function(res) {
        if (!res.ok) {
          if (res.status === 401 || res.status === 403) {
            throw new Error('PRO_REQUIRED');
          }
          throw new Error('AUDIO_FETCH_FAILED');
        }
        return res.blob();
      })
      .then(function(blob) {
        return URL.createObjectURL(blob);
      });
  }

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
    if (currentPlayBtn) {
      currentPlayBtn.classList.remove('loading');
      currentPlayBtn.innerHTML = '<span class="play-icon">' + icon + '</span>';
    }
    const mpb = getMiniEl('miniPlayBtn');
    if (mpb) {
      mpb.classList.remove('loading');
      mpb.innerHTML = '<span class="play-icon">' + icon + '</span>';
    }
  }

  // ローディング状態の表示
  function showLoading(btn) {
    if (btn) {
      btn.classList.add('loading');
      btn.innerHTML = '';
    }
    const mpb = getMiniEl('miniPlayBtn');
    if (mpb) {
      mpb.classList.add('loading');
      mpb.innerHTML = '';
    }
  }

  // バッファリング状態の表示
  function setBuffering(buffering) {
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      if (card) {
        const fill = card.querySelector('.progress-fill');
        if (fill) fill.classList.toggle('buffering', buffering);
      }
    }
    const mpf = getMiniEl('miniProgressFill');
    if (mpf) mpf.classList.toggle('buffering', buffering);
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
    var base = location.origin + '/';
    navigator.mediaSession.metadata = new MediaMetadata({
      title: title, artist: 'DeepCast AI', album: 'AIポッドキャスト',
      artwork: [
        { src: base + 'assets/cover-podcast.svg', sizes: '512x512', type: 'image/svg+xml' },
        { src: base + 'assets/icon.svg', sizes: '96x96', type: 'image/svg+xml' }
      ]
    });
    navigator.mediaSession.setActionHandler('play', function() { audioEl.play(); updatePlayIcons(true); });
    navigator.mediaSession.setActionHandler('pause', function() { audioEl.pause(); updatePlayIcons(false); });
    navigator.mediaSession.setActionHandler('stop', stopCurrent);
    navigator.mediaSession.setActionHandler('seekbackward', function() { audioEl.currentTime = Math.max(0, audioEl.currentTime - 10); });
    navigator.mediaSession.setActionHandler('seekforward', function() { audioEl.currentTime = Math.min(audioEl.duration || 0, audioEl.currentTime + 10); });
    navigator.mediaSession.setActionHandler('seekto', function(d) { if (d.seekTime != null) audioEl.currentTime = d.seekTime; });
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
    var src = item.audio;
    if (src && !src.startsWith('http') && !src.startsWith('/')) src = '/' + src;
    // 即時フィードバック: ローディング状態を表示
    item.btn.classList.add('playing');
    showLoading(item.btn);
    // 認証付き音声取得（API経由の場合Blob URLに変換）
    resolveAudioSrc(src).then(function(resolvedUrl) {
      audioEl.src = resolvedUrl;
      return audioEl.play();
    }).catch(function(err) {
      var card = item.btn.closest('.episode-card');
      if (card) {
        var timeEl = card.querySelector('.progress-time');
        if (timeEl) {
          if (err && err.message === 'PRO_REQUIRED') {
            timeEl.innerHTML = '<span class="player-error-msg">このエピソードはProプラン限定です。</span>';
          } else {
            timeEl.innerHTML = '<span class="player-error-msg">エピソードの読み込みに失敗しました。ページを再読み込みしてください。</span>';
          }
        }
      }
      item.btn.classList.remove('loading');
      currentPlayBtn = null;
    });
    setMediaSession(item.title);
    const mt = getMiniEl('miniTitle');
    if (mt) mt.textContent = item.title;
    showMiniPlayer();
  }

  function bindPlayer(btn, audioSrc, title) {
    // ARIA属性の設定
    btn.setAttribute('role', 'button');
    btn.setAttribute('aria-label', '再生: ' + title);
    btn.setAttribute('tabindex', '0');

    // キーボード操作対応（スペースキー/Enterで再生/停止）
    btn.addEventListener('keydown', function(e) {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        btn.click();
      }
    });

    btn.addEventListener('click', function() {
      // 二重クリック防止
      if (btn.classList.contains('loading')) return;

      const card = btn.closest('.episode-card');
      const timeEl = card ? card.querySelector('.progress-time') : null;
      if (currentPlayBtn === btn) {
        if (audioEl.paused) {
          audioEl.play();
          updatePlayIcons(true);
          btn.setAttribute('aria-label', '一時停止: ' + title);
        } else {
          audioEl.pause();
          updatePlayIcons(false);
          btn.setAttribute('aria-label', '再生: ' + title);
        }
        return;
      }
      resetCardUI(currentPlayBtn);
      audioEl.pause();
      audioEl.currentTime = 0;
      if (!audioSrc) { if (timeEl) timeEl.textContent = '音声ファイル未設定'; return; }
      const idx = playlist.findIndex(function(p) { return p.btn === btn; });
      playlistIndex = idx >= 0 ? idx : -1;
      currentPlayBtn = btn;
      currentAudioSrc = audioSrc;
      currentTitleText = title;
      // 相対パスをルートからの絶対パスに変換（SPA遷移でbaseがズレるのを防止）
      var resolvedSrc = audioSrc;
      if (audioSrc && !audioSrc.startsWith('http') && !audioSrc.startsWith('/')) {
        resolvedSrc = '/' + audioSrc;
      }
      // 即時フィードバック: ボタンアイコンを即座に変更しローディング表示
      btn.classList.add('playing');
      showLoading(btn);
      btn.setAttribute('aria-label', '読み込み中: ' + title);
      // 認証付き音声取得（API経由の場合Blob URLに変換）
      resolveAudioSrc(resolvedSrc).then(function(blobUrl) {
        audioEl.src = blobUrl;
        // play()をクリック直後に呼ぶ（ユーザージェスチャーコンテキスト内で実行）
        return audioEl.play();
      }).catch(function(err) {
        if (timeEl) {
          if (err && err.message === 'PRO_REQUIRED') {
            timeEl.innerHTML = '<span class="player-error-msg">このエピソードはProプラン限定です。</span>';
          } else {
            timeEl.innerHTML = '<span class="player-error-msg">エピソードの読み込みに失敗しました。ページを再読み込みしてください。</span>';
          }
        }
        btn.classList.remove('loading', 'playing');
        btn.setAttribute('aria-label', '再生: ' + title);
        currentPlayBtn = null;
      });
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
    episodeList.querySelectorAll('.play-btn').forEach(function(btn) {
      if (btn.closest('.episode-card').style.display !== 'none') {
        playlist.push({ btn: btn, audio: btn.dataset.audio || '', title: btn.dataset.title || '' });
      }
    });
  }

  // --- canplay: ローディング完了 → アイコンを再生中に切り替え ---
  audioEl.addEventListener('canplay', function() {
    updatePlayIcons(!audioEl.paused);
    setBuffering(false);
  });

  // --- playing: 再生開始（バッファリング解除） ---
  audioEl.addEventListener('playing', function() {
    updatePlayIcons(true);
    setBuffering(false);
    if (currentPlayBtn) {
      currentPlayBtn.setAttribute('aria-label', '一時停止: ' + currentTitleText);
    }
  });

  // --- waiting: バッファリング中 ---
  audioEl.addEventListener('waiting', function() {
    setBuffering(true);
  });

  // --- error: 再生エラーの親切なメッセージ ---
  audioEl.addEventListener('error', function() {
    if (currentPlayBtn) {
      currentPlayBtn.classList.remove('loading', 'playing');
      currentPlayBtn.innerHTML = '<span class="play-icon">&#9654;</span>';
      var card = currentPlayBtn.closest('.episode-card');
      if (card) {
        var timeEl = card.querySelector('.progress-time');
        if (timeEl) {
          timeEl.innerHTML = '<span class="player-error-msg">エピソードの読み込みに失敗しました。ページを再読み込みしてください。</span>';
        }
      }
    }
    setBuffering(false);
    hideMiniPlayer();
    currentPlayBtn = null;
  });

  // --- timeupdate イベント（2:30で強制終了） ---
  audioEl.addEventListener('timeupdate', function() {
    if (!audioEl.duration) return;
    // 2:30制限: 上限に達したら再生終了イベントを発火
    if (audioEl.currentTime >= MAX_DURATION_SEC) {
      audioEl.pause();
      audioEl.currentTime = 0;
      audioEl.dispatchEvent(new Event('ended'));
      return;
    }
    const pct = (audioEl.currentTime / audioEl.duration * 100) + '%';
    const timeStr = formatTime(audioEl.currentTime) + ' / ' + formatTime(audioEl.duration);
    // ミニプレイヤー
    const mpf = getMiniEl('miniProgressFill');
    const mtime = getMiniEl('miniTime');
    if (mpf) mpf.style.width = pct;
    if (mtime) mtime.textContent = timeStr;
    // エピソードカード（ホーム/全エピソードページ）
    if (currentPlayBtn) {
      const card = currentPlayBtn.closest('.episode-card');
      if (card) {
        const fill = card.querySelector('.progress-fill');
        const timeEl = card.querySelector('.progress-time');
        if (fill) fill.style.width = pct;
        if (timeEl) timeEl.textContent = timeStr;
      }
    }
    // 記事ページプレイヤー
    const artFill = document.getElementById('articleProgressFill');
    const artTime = document.getElementById('articleProgressTime');
    if (artFill || artTime) {
      const artBtn = document.getElementById('articlePlayBtn');
      if (artBtn && audioFileName(artBtn.dataset.audio) === audioFileName(currentAudioSrc)) {
        if (artFill) artFill.style.width = pct;
        if (artTime) artTime.textContent = timeStr;
      }
    }
    // 同じ音声の全再生ボタンの進捗を同期
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

  // --- 再生終了 → 次のエピソードへ自動遷移＆自動再生 ---
  audioEl.addEventListener('ended', function() {
    var finishedAudio = currentAudioSrc;
    resetCardUI(currentPlayBtn);
    currentPlayBtn = null;
    updatePlayIcons(false);

    // アクティブタブ時のみ記事ページへ遷移（バックグラウンドではスキップ）
    if (document.visibilityState === 'visible') {
      var articleUrl = audioToArticle[audioFileName(finishedAudio)];
      if (articleUrl) {
        var normPath = function(p) { return p.replace(/\/index\.html$/, '/').replace(/^\//, '').replace(/\/$/, '') || ''; };
        var currentPath = normPath(location.pathname);
        var targetPath = normPath(articleUrl);
        if (currentPath !== targetPath) {
          // SPAルーター経由で遷移
          if (window.DeepCastRouter && window.DeepCastRouter.navigateTo) {
            window.DeepCastRouter.navigateTo(articleUrl, true);
          }
        }
      }
    }

    // 次のエピソードを自動再生（ページ遷移が落ち着くまで少し待つ）
    const nextIdx = playlistIndex + 1;
    if (nextIdx < playlist.length) {
      setTimeout(function() { playFromPlaylist(nextIdx); }, 800);
    } else {
      playlistIndex = -1;
      hideMiniPlayer();
    }
  });

  // --- ミニプレイヤーのコントロールをバインド（イベント委譲方式） ---
  // ミニプレイヤーは#miniPlayer要素に1度だけイベント委譲を設定し、
  // SPA遷移でDOMが置き換わってもリスナーが蓄積しないようにする
  var miniPlayerDelegated = false;

  function bindMiniPlayer() {
    var mp = getMiniEl('miniPlayer');

    // イベント委譲は初回のみ設定（SPA遷移で再設定不要）
    if (mp && !miniPlayerDelegated) {
      mp.addEventListener('click', function(e) {
        var target = e.target.closest('#miniPlayBtn, #miniCloseBtn, #miniProgressBar');
        if (!target) return;

        if (target.id === 'miniPlayBtn') {
          if (!audioEl.src) return;
          if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
          else { audioEl.pause(); updatePlayIcons(false); }
        } else if (target.id === 'miniCloseBtn') {
          stopCurrent();
        } else if (target.id === 'miniProgressBar') {
          if (!audioEl.duration) return;
          var rect = target.getBoundingClientRect();
          audioEl.currentTime = ((e.clientX - rect.left) / rect.width) * audioEl.duration;
        }
      });

      // ミニプレイヤーのキーボード操作
      mp.addEventListener('keydown', function(e) {
        var target = e.target.closest('#miniPlayBtn, #miniProgressBar');
        if (!target) return;

        if (target.id === 'miniPlayBtn' && (e.key === ' ' || e.key === 'Enter')) {
          e.preventDefault();
          if (!audioEl.src) return;
          if (audioEl.paused) { audioEl.play(); updatePlayIcons(true); }
          else { audioEl.pause(); updatePlayIcons(false); }
        } else if (target.id === 'miniProgressBar') {
          if (!audioEl.duration) return;
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            audioEl.currentTime = Math.min(audioEl.duration, audioEl.currentTime + 5);
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            audioEl.currentTime = Math.max(0, audioEl.currentTime - 5);
          }
        }
      });
      miniPlayerDelegated = true;
    }

    // 音量コントロールの初期化
    initVolumeControl();
    var muteBtn = document.getElementById('miniMuteBtn');
    if (muteBtn && !muteBtn._bound) {
      muteBtn.addEventListener('click', toggleMute);
      muteBtn._bound = true;
    }

    // 再生中ならミニプレイヤーの状態を復元
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

  // --- SPA遷移後に再生中ボタンを新しいDOMに再関連付け ---
  function reassociatePlayingButton() {
    // 全再生ボタンをリセット
    document.querySelectorAll('.play-btn').forEach(function(btn) {
      btn.classList.remove('playing');
      btn.innerHTML = '<span class="play-icon">&#9654;</span>';
      var card = btn.closest('.episode-card');
      if (card) {
        var fill = card.querySelector('.progress-fill');
        if (fill) fill.style.width = '0%';
      }
    });

    if (!currentAudioSrc || (audioEl.paused && audioEl.currentTime === 0)) return;
    var btns = document.querySelectorAll('.play-btn[data-audio]');
    var found = false;
    btns.forEach(function(btn) {
      if (audioFileName(btn.dataset.audio) === audioFileName(currentAudioSrc)) {
        currentPlayBtn = btn;
        btn.classList.add('playing');
        updatePlayIcons(!audioEl.paused);
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
      currentPlayBtn = null;
    }
    buildPlaylist();
    if (currentPlayBtn) {
      const idx = playlist.findIndex(function(p) { return p.btn === currentPlayBtn; });
      playlistIndex = idx >= 0 ? idx : -1;
    }
  }

  // --- オフライン検出・案内 ---
  function createOfflineBanner() {
    if (document.getElementById('offlineBanner')) return;
    var banner = document.createElement('div');
    banner.id = 'offlineBanner';
    banner.className = 'offline-banner';
    banner.setAttribute('role', 'alert');
    banner.textContent = 'インターネットに接続されていません。接続を確認してください。';
    document.body.appendChild(banner);
  }

  function showOfflineBanner() {
    createOfflineBanner();
    var banner = document.getElementById('offlineBanner');
    if (banner) {
      requestAnimationFrame(function() { banner.classList.add('visible'); });
    }
  }

  function hideOfflineBanner() {
    var banner = document.getElementById('offlineBanner');
    if (banner) banner.classList.remove('visible');
  }

  window.addEventListener('offline', showOfflineBanner);
  window.addEventListener('online', hideOfflineBanner);
  // 初期チェック
  if (!navigator.onLine) {
    document.addEventListener('DOMContentLoaded', showOfflineBanner);
  }

  // --- 音量調整 ---
  // ミニプレイヤーの音量スライダーを初期化
  function initVolumeControl() {
    var slider = document.getElementById('miniVolumeSlider');
    if (!slider) return;
    slider.value = audioEl.volume * 100;
    // input と change の両方で即時反映
    slider.addEventListener('input', function() {
      audioEl.volume = this.value / 100;
      audioEl.muted = false;
    });
  }

  // 音量ミュートトグル
  function toggleMute() {
    audioEl.muted = !audioEl.muted;
    var btn = document.getElementById('miniMuteBtn');
    if (btn) {
      btn.innerHTML = audioEl.muted ? '&#128263;' : '&#128266;';
      btn.setAttribute('aria-label', audioEl.muted ? 'ミュート解除' : 'ミュート');
    }
  }

  // --- グローバルオブジェクトとして公開 ---
  window.DeepCastAudio = {
    audioEl: audioEl,
    get currentPlayBtn() { return currentPlayBtn; },
    set currentPlayBtn(v) { currentPlayBtn = v; },
    get playlist() { return playlist; },
    set playlist(v) { playlist = v; },
    get playlistIndex() { return playlistIndex; },
    set playlistIndex(v) { playlistIndex = v; },
    get audioToArticle() { return audioToArticle; },
    bindPlayer: bindPlayer,
    buildPlaylist: buildPlaylist,
    stopCurrent: stopCurrent,
    formatTime: formatTime,
    resetCardUI: resetCardUI,
    showMiniPlayer: showMiniPlayer,
    hideMiniPlayer: hideMiniPlayer,
    updatePlayIcons: updatePlayIcons,
    playFromPlaylist: playFromPlaylist,
    setMediaSession: setMediaSession,
    bindMiniPlayer: bindMiniPlayer,
    reassociatePlayingButton: reassociatePlayingButton,
    audioFileName: audioFileName,
    initVolumeControl: initVolumeControl,
    toggleMute: toggleMute
  };

})();
