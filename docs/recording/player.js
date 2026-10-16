// TRACE 20k Local Run Terminal Player
// Strictly offline, vanilla JS, textContent only (no HTML injection, deterministic ANSI escape stripping)
(function () {
  'use strict';

  var ansiRegex = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;

  function stripAnsi(str) {
    return str.replace(ansiRegex, '');
  }

  var events = [];
  var totalDuration = 0;
  var currentIndex = 0;
  var currentTime = 0;
  var isPlaying = false;
  var playbackSpeed = 1.0;
  var timerId = null;
  var lastWallTime = 0;

  var outputEl = document.getElementById('terminal-output');
  var viewportEl = document.getElementById('terminal-viewport');
  var playBtn = document.getElementById('btn-play');
  var restartBtn = document.getElementById('btn-restart');
  var progressEl = document.getElementById('progress-slider');
  var timeEl = document.getElementById('time-display');
  var speedSelect = document.getElementById('speed-select');

  function formatTime(s) {
    var mins = Math.floor(s / 60);
    var secs = Math.floor(s % 60);
    var ms = Math.floor((s % 1) * 10);
    return (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs + '.' + ms;
  }

  function renderUpToTime(targetTime) {
    var accumulated = '';
    var newIdx = 0;
    for (var i = 0; i < events.length; i++) {
      if (events[i][0] <= targetTime) {
        accumulated += stripAnsi(events[i][2]);
        newIdx = i + 1;
      } else {
        break;
      }
    }
    currentIndex = newIdx;
    currentTime = targetTime;
    outputEl.textContent = accumulated;
    viewportEl.scrollTop = viewportEl.scrollHeight;

    progressEl.value = totalDuration > 0 ? (currentTime / totalDuration) * 100 : 0;
    timeEl.textContent = formatTime(currentTime) + ' / ' + formatTime(totalDuration);
  }

  function tick() {
    if (!isPlaying) return;
    var now = performance.now();
    var delta = (now - lastWallTime) / 1000 * playbackSpeed;
    lastWallTime = now;

    var targetTime = currentTime + delta;
    if (targetTime >= totalDuration) {
      targetTime = totalDuration;
      renderUpToTime(targetTime);
      pause();
      return;
    }

    renderUpToTime(targetTime);
    timerId = requestAnimationFrame(tick);
  }

  function play() {
    if (currentTime >= totalDuration) {
      renderUpToTime(0);
    }
    isPlaying = true;
    lastWallTime = performance.now();
    playBtn.textContent = 'Pause';
    playBtn.setAttribute('aria-label', 'Pause playback');
    timerId = requestAnimationFrame(tick);
  }

  function pause() {
    isPlaying = false;
    if (timerId) {
      cancelAnimationFrame(timerId);
      timerId = null;
    }
    playBtn.textContent = 'Play';
    playBtn.setAttribute('aria-label', 'Start playback');
  }

  function togglePlay() {
    if (isPlaying) {
      pause();
    } else {
      play();
    }
  }

  function seek(percent) {
    var target = (percent / 100) * totalDuration;
    renderUpToTime(target);
  }

  playBtn.addEventListener('click', togglePlay);
  restartBtn.addEventListener('click', function () {
    pause();
    renderUpToTime(0);
    play();
  });

  progressEl.addEventListener('input', function (e) {
    pause();
    seek(parseFloat(e.target.value));
  });

  speedSelect.addEventListener('change', function (e) {
    playbackSpeed = parseFloat(e.target.value);
  });

  // Load asciicast v2 file
  var castFile = 'run20k.cast';
  fetch(castFile)
    .catch(function () { return fetch('run3_final_fresh20k.cast'); })
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.text();
    })
    .then(function (text) {
      var lines = text.split('\n');
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;
        try {
          var item = JSON.parse(line);
          if (Array.isArray(item) && item.length >= 3 && item[1] === 'o') {
            events.push(item);
          }
        } catch (e) {}
      }
      if (events.length > 0) {
        totalDuration = events[events.length - 1][0];
      }
      renderUpToTime(totalDuration); // Show completed terminal by default
      pause();
    })
    .catch(function (err) {
      outputEl.textContent = 'Failed to load recording: ' + err.message;
    });
})();
