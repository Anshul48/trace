// TRACE 20k Local Run Terminal Player
// Strictly offline, vanilla JS, textContent only (no HTML injection,
// deterministic ANSI escape stripping). No autoplay: playback starts
// only on an explicit Play press, and first paint is t=0 (empty terminal).
(function () {
  'use strict';

  var ansiRegex = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;

  function stripAnsi(str) {
    return str.replace(ansiRegex, '');
  }

  // Chapters derived strictly from real run20k.cast event times/content.
  var chapters = [
    { t: 0, title: 'Setup: Python check, isolated environment',
      caption: 't=0.0s: [1/7] Python 3.12.3 found, uv located; [2/7] isolated venv created at .trace-demo-env.' },
    { t: 0.129, title: 'Dependencies and freeze check',
      caption: 't=0.1s: [3/7] numpy + blake3 installed; [4/7] freeze check entries=207 ok=207 missing=0 mismatch=0.' },
    { t: 0.485, title: 'Prefix data verification: 8 gates PASS',
      caption: 't=0.5s: [5/7] 20,030 tokens, 88 documents, 144 atoms; all 8 prefix gates PASS; VERIFY PASS.' },
    { t: 1.094, title: 'Pilot run: drain, faults, recovery, PASS',
      caption: 't=1.1s: [6/7] drain cycles to 0 remaining, append ACK 0.022s, SIGKILL/restart clean, status PASS (25.9s wall).' },
    { t: 27.56, title: 'Export viewer data, finish',
      caption: 't=27.6s: local_20k_data.json exported (262,412 bytes, 240 queries); [7/7] server skipped (--no-server).' }
  ];

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
  var resetBtn = document.getElementById('btn-reset');
  var stepBackBtn = document.getElementById('btn-step-back');
  var stepFwdBtn = document.getElementById('btn-step-fwd');
  var progressEl = document.getElementById('progress-slider');
  var timeEl = document.getElementById('time-display');
  var speedSelect = document.getElementById('speed-select');
  var stepEl = document.getElementById('step-counter');
  var captionEl = document.getElementById('chapter-caption');
  var chapterListEl = document.getElementById('chapter-list');
  var ticksEl = document.getElementById('chapter-ticks');

  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function formatTime(s) {
    var mins = Math.floor(s / 60);
    var secs = Math.floor(s % 60);
    var ms = Math.floor((s % 1) * 10);
    return (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs + '.' + ms;
  }

  function chapterIndexAt(t) {
    var idx = 0;
    for (var i = 0; i < chapters.length; i++) {
      if (t >= chapters[i].t) idx = i;
    }
    return idx;
  }

  function buildChapterList() {
    if (!chapterListEl) return;
    chapterListEl.textContent = '';
    for (var i = 0; i < chapters.length; i++) {
      (function (i) {
        var li = document.createElement('li');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'chapter-btn';
        btn.setAttribute('data-chapter', String(i + 1));
        btn.textContent = chapters[i].title + ' (' + formatTime(chapters[i].t) + ')';
        btn.setAttribute('aria-label', 'Jump replay to chapter ' + (i + 1) + ' of ' +
          chapters.length + ': ' + chapters[i].title);
        btn.addEventListener('click', function () {
          pause();
          renderUpToTime(chapters[i].t);
        });
        li.appendChild(btn);
        chapterListEl.appendChild(li);
      })(i);
    }
  }

  function markActiveChapter(idx) {
    if (!chapterListEl) return;
    var btns = chapterListEl.querySelectorAll('.chapter-btn');
    for (var i = 0; i < btns.length; i++) {
      if (i === idx) btns[i].setAttribute('aria-current', 'true');
      else btns[i].removeAttribute('aria-current');
    }
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

    var ci = chapterIndexAt(currentTime);
    if (stepEl) stepEl.textContent = 'Chapter ' + (ci + 1) + ' of ' + chapters.length;
    if (captionEl) captionEl.textContent = chapters[ci].caption;
    markActiveChapter(ci);
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
    playBtn.setAttribute('aria-label', 'Pause the recorded 20K run replay');
    if (reduceMotion) {
      // Reduced motion: advance in coarser steps to limit visual churn.
      playbackSpeed = 1.0;
      if (speedSelect) speedSelect.value = '1.0';
    }
    timerId = requestAnimationFrame(tick);
  }

  function pause() {
    isPlaying = false;
    if (timerId) {
      cancelAnimationFrame(timerId);
      timerId = null;
    }
    playBtn.textContent = 'Play';
    playBtn.setAttribute('aria-label', 'Play replay of the recorded real 20K run (27.8 seconds)');
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

  function stepChapter(dir) {
    var ci = chapterIndexAt(currentTime);
    var next = ci + dir;
    if (next < 0) next = 0;
    if (next >= chapters.length) next = chapters.length - 1;
    pause();
    renderUpToTime(chapters[next].t);
  }

  function renderTicks() {
    if (!ticksEl || !(totalDuration > 0)) return;
    ticksEl.textContent = '';
    for (var i = 1; i < chapters.length; i++) {
      var pct = (chapters[i].t / totalDuration) * 100;
      if (pct < 0) pct = 0;
      if (pct > 100) pct = 100;
      var tick = document.createElement('span');
      tick.className = 'chapter-tick';
      tick.style.left = pct.toFixed(2) + '%';
      ticksEl.appendChild(tick);
    }
  }

  playBtn.addEventListener('click', togglePlay);
  restartBtn.addEventListener('click', function () {
    pause();
    renderUpToTime(0);
    play();
  });
  if (resetBtn) resetBtn.addEventListener('click', function () {
    pause();
    renderUpToTime(0);
  });
  if (stepBackBtn) stepBackBtn.addEventListener('click', function () {
    stepChapter(-1);
  });
  if (stepFwdBtn) stepFwdBtn.addEventListener('click', function () {
    stepChapter(1);
  });
  document.addEventListener('keydown', function (e) {
    if (!outputEl) return;
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    if (e.key === ' ') {
      e.preventDefault();
      togglePlay();
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      stepChapter(1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      stepChapter(-1);
    } else if (e.key === 'r' || e.key === 'R') {
      pause();
      renderUpToTime(0);
    }
  });

  progressEl.addEventListener('input', function (e) {
    pause();
    seek(parseFloat(e.target.value));
  });

  speedSelect.addEventListener('change', function (e) {
    playbackSpeed = parseFloat(e.target.value);
  });

  buildChapterList();
  // First paint before the capture loads: t=0 state with chapter 1 shown.
  renderUpToTime(0);

  // Load asciicast v2 file (single canonical capture).
  fetch('run20k.cast')
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
      renderTicks();
      renderUpToTime(0); // First paint at t=0: empty terminal, Chapter 1 of 5
      pause();
    })
    .catch(function (err) {
      outputEl.textContent = 'Failed to load recording: ' + err.message +
        '. You can still download the raw capture (run20k.cast link above).';
    });
})();
