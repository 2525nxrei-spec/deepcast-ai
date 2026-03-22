// ===================================================================
//  DeepCast AI - Entry Point
//  iOS Safari音声アンロック、Service Worker登録
//  各モジュール: audio-player.js → page-init.js → spa-router.js
// ===================================================================

(function () {
  'use strict';

  // ===== iOS Safari 音声アンロック =====
  var unlocked = false;
  function unlockAudio() {
    if (unlocked) return;
    unlocked = true;
    var a = new Audio();
    a.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
    a.play().then(function() { a.pause(); }).catch(function() {});
    document.removeEventListener('touchstart', unlockAudio, true);
    document.removeEventListener('click', unlockAudio, true);
  }
  document.addEventListener('touchstart', unlockAudio, true);
  document.addEventListener('click', unlockAudio, true);

  // ===== Service Worker 登録 =====
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(function() {});
  }

})();
