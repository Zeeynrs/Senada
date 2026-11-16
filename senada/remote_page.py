"""The phone remote's page (see remote.py): one self-contained HTML file, no outside files."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d0d0f">
<title>Senada</title>
<style>
  :root { --bg:#0d0d0f; --panel:#16161b; --ink:#f5f5f7; --dim:#9898a6; --line:#282830; --hi:#ff2d55; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--ink);
              font-family:system-ui,-apple-system,sans-serif; overscroll-behavior:none; }
  body { display:flex; flex-direction:column; align-items:center;
         padding:12px 16px max(16px,env(safe-area-inset-bottom)); }
  .wrap { position:relative; width:100%; max-width:440px; flex:1; min-height:0;
          display:flex; flex-direction:column; gap:12px; }
  .bg { position:fixed; inset:0; background-size:cover; background-position:center;
        filter:blur(70px) brightness(.32); transform:scale(1.2); opacity:.8; pointer-events:none;
        transition:background-image .6s; }
  .tabs { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; background:rgba(255,255,255,.06);
          border:1px solid var(--line); border-radius:14px; padding:4px; flex-shrink:0; }
  .tab { height:34px; border:0; border-radius:10px; background:none; color:var(--dim);
         font:600 13px/1 inherit; cursor:pointer; }
  .tab.active { background:var(--ink); color:#000; }
  .view { display:none; flex:1; min-height:0; flex-direction:column; }
  .view.active { display:flex; }
  #v-player { justify-content:space-between; gap:12px; }
  .art { width:100%; aspect-ratio:1; max-height:310px; align-self:center; border-radius:18px;
         background:var(--panel); overflow:hidden; display:grid; place-items:center;
         box-shadow:0 20px 50px rgba(0,0,0,.55); }
  .art img { width:100%; height:100%; object-fit:cover; display:block; }
  .art svg { width:34%; opacity:.22; }
  .meta { display:flex; align-items:center; gap:12px; min-height:52px; }
  .titles { flex:1; min-width:0; }
  .name { font-size:20px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .artist { font-size:14px; color:var(--dim); margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .bar input { width:100%; }
  .times { display:flex; justify-content:space-between; font-size:12px; color:var(--dim); font-variant-numeric:tabular-nums; }
  .keys { display:flex; align-items:center; justify-content:space-between; padding:2px 0; }
  .vol { display:flex; align-items:center; gap:10px; color:var(--dim); }
  .vol input { flex:1; }
  button { background:none; border:0; color:inherit; padding:0; cursor:pointer;
           display:inline-flex; align-items:center; justify-content:center; border-radius:99px; }
  .keys button { width:46px; height:46px; }
  .keys .main { width:64px; height:64px; background:var(--ink); color:#000; }
  button.on { color:var(--hi); }
  button:active { transform:scale(.92); }
  button svg { width:22px; height:22px; fill:currentColor; }
  .keys .main svg { width:28px; height:28px; }
  input[type=range] { -webkit-appearance:none; appearance:none; height:4px; border-radius:4px;
                      background:var(--line); outline:none; }
  input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; width:16px; height:16px;
                                            border-radius:50%; background:var(--ink); }
  .scroll { flex:1; min-height:0; overflow-y:auto; padding:4px 2px 12px; }
  .lyr-line { padding:8px 10px; border-radius:10px; color:var(--dim); font-size:16px; line-height:1.45;
              transition:color .2s, background .2s; }
  .lyr-line.on { color:var(--ink); font-weight:700; font-size:18px; background:rgba(255,255,255,.07); }
  .lyr-sub { font-size:12px; color:var(--dim); margin-top:2px; font-weight:400; }
  .q-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:4px 2px 10px;
            flex-shrink:0; }
  .q-pill { padding:6px 12px; border-radius:99px; background:rgba(255,255,255,.08);
            border:1px solid var(--line); font:600 12px/1 inherit; color:var(--ink); }
  .q-pill.on { background:var(--hi); border-color:var(--hi); color:#fff; }
  .q-row { display:flex; align-items:center; gap:10px; padding:10px; border-radius:12px;
           cursor:pointer; }
  .q-row:active, .q-row:hover { background:rgba(255,255,255,.06); }
  .q-info { flex:1; min-width:0; }
  .q-title { font-size:14px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .q-sub { font-size:12px; color:var(--dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
  .q-del { width:34px; height:34px; color:var(--dim); flex-shrink:0; }
  .empty { text-align:center; color:var(--dim); padding:32px 16px; font-size:14px; }
</style>
</head>
<body>
<div class="bg" id="bg"></div>
<div class="wrap">
  <div class="tabs">
    <button class="tab active" id="tab-player" onclick="setTab('player')">Player</button>
    <button class="tab" id="tab-lyrics" onclick="setTab('lyrics')">Lyrics</button>
    <button class="tab" id="tab-queue" onclick="setTab('queue')">Queue</button>
  </div>

  <div class="view active" id="v-player">
    <div class="art" id="art">
      <svg viewBox="0 0 24 24"><path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z" fill="currentColor"/></svg>
    </div>
    <div>
      <div class="meta">
        <div class="titles"><div class="name" id="name">Senada</div><div class="artist" id="artist">Nothing playing</div></div>
        <button id="like" onclick="cmd('like')" aria-label="Like"></button>
      </div>
      <div class="bar">
        <input id="seek" type="range" min="0" max="1000" value="0">
        <div class="times"><span id="pos">0:00</span><span id="dur">0:00</span></div>
      </div>
    </div>
    <div class="keys">
      <button id="shuf" onclick="cmd('shuffle')" aria-label="Shuffle"></button>
      <button onclick="cmd('previous')" aria-label="Previous"></button>
      <button id="play" class="main" onclick="cmd('toggle')" aria-label="Play or pause"></button>
      <button onclick="cmd('next')" aria-label="Next"></button>
      <button id="rep" onclick="cmd('repeat')" aria-label="Repeat"></button>
    </div>
    <div class="vol">
      <svg viewBox="0 0 24 24" width="20" height="20"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02z" fill="currentColor"/></svg>
      <input id="vol" type="range" min="0" max="100" value="80">
    </div>
  </div>

  <div class="view" id="v-lyrics">
    <div class="scroll" id="lyr-list"><div class="empty">Waiting for lyrics…</div></div>
  </div>

  <div class="view" id="v-queue">
    <div class="q-head">
      <button class="q-pill" id="q-auto" onclick="cmd('autoplay')">Autoplay</button>
      <button class="q-pill" id="q-clear" onclick="cmd('clear_queue')">Clear queue</button>
    </div>
    <div class="scroll" id="q-list"><div class="empty">Queue is empty</div></div>
  </div>
</div>

<script>
const I = {
  play:'<path d="M8 5v14l11-7z"/>',
  pause:'<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>',
  prev:'<path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/>',
  next:'<path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>',
  shuf:'<path d="M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/>',
  rep:'<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"/>',
  rep1:'<path d="M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-2V9h-1l-2 1v1h1.5v4H13z"/>',
  heart:'<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>',
  heart0:'<path d="M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z"/>',
  del:'<path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>'
};
const svg = p => '<svg viewBox="0 0 24 24">' + p + '</svg>';
const $ = id => document.getElementById(id);
const key = new URLSearchParams(location.search).get('k') || '';
const api = p => p + '?k=' + encodeURIComponent(key);
const esc = s => String(s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
$('shuf').innerHTML = svg(I.shuf);
document.querySelector('[onclick*="previous"]').innerHTML = svg(I.prev);
document.querySelector('[onclick*="next"]').innerHTML = svg(I.next);

let tab = 'player', state = {}, seeking = false, voling = false, shownImg = '', lastLyrKey = '', lastCur = -99, lastQKey = '';
const fmt = ms => { const s = Math.max(0, Math.floor(ms/1000)); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); };
function setTab(t) {
  tab = t;
  ['player','lyrics','queue'].forEach(k => {
    $('tab-' + k).classList.toggle('active', k === t);
    $('v-' + k).classList.toggle('active', k === t);
  });
  if (t === 'lyrics') pollLyrics();
  if (t === 'queue') pollQueue();
}
function cmd(c, v) {
  fetch(api('/api/cmd'), {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(v === undefined ? {cmd:c} : {cmd:c, value:v})})
    .then(() => { setTimeout(poll, 120); if (tab === 'queue') setTimeout(pollQueue, 150); });
}
function paint(s) {
  state = s;
  $('name').textContent = s.hasTrack ? s.name : 'Senada';
  $('artist').textContent = s.hasTrack ? s.artists : 'Nothing playing';
  $('play').innerHTML = svg(s.isPlaying ? I.pause : I.play);
  $('like').innerHTML = svg(s.liked ? I.heart : I.heart0);
  $('like').classList.toggle('on', !!s.liked);
  $('shuf').classList.toggle('on', !!s.shuffle);
  $('rep').innerHTML = svg(s.repeat === 'track' ? I.rep1 : I.rep);
  $('rep').classList.toggle('on', s.repeat && s.repeat !== 'off');
  $('q-auto').classList.toggle('on', !!s.autoplay);
  if (!seeking) { $('seek').max = s.duration || 1000; $('seek').value = s.position || 0; $('pos').textContent = fmt(s.position||0); }
  $('dur').textContent = fmt(s.duration || 0);
  if (!voling) $('vol').value = s.volume || 0;
  if (s.image !== shownImg) {
    shownImg = s.image;
    $('art').innerHTML = s.image ? '<img src="'+esc(s.image)+'">' : '<svg viewBox="0 0 24 24"><path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z" fill="currentColor"/></svg>';
    $('bg').style.backgroundImage = s.image ? 'url("'+s.image+'")' : 'none';
  }
}
function paintLyrics(d) {
  const sig = d.status + ':' + (d.lines ? d.lines.length : 0) + ':' + (d.lines && d.lines[0] ? d.lines[0].text : '');
  const el = $('lyr-list');
  if (sig !== lastLyrKey) {
    lastLyrKey = sig;
    lastCur = -99;
    if (!d.lines || !d.lines.length) {
      el.innerHTML = '<div class="empty">' + (d.status === 'loading' ? 'Loading lyrics…' : 'No lyrics available') + '</div>';
      return;
    }
    el.innerHTML = d.lines.map((l, i) => '<div class="lyr-line" id="ll-' + i + '">' + esc(l.text) + (l.sub ? '<div class="lyr-sub">' + esc(l.sub) + '</div>' : '') + '</div>').join('');
  }
  if (d.synced && d.current !== lastCur) {
    if (lastCur >= 0) { const old = $('ll-' + lastCur); if (old) old.classList.remove('on'); }
    lastCur = d.current;
    if (lastCur >= 0) {
      const cur = $('ll-' + lastCur);
      if (cur) { cur.classList.add('on'); cur.scrollIntoView({block:'center', behavior:'smooth'}); }
    }
  }
}
function paintQueue(d) {
  $('q-auto').classList.toggle('on', !!d.autoplay);
  $('q-clear').style.display = d.queue && d.queue.length ? 'inline-flex' : 'none';
  const sig = JSON.stringify(d.queue || []);
  if (sig === lastQKey) return;
  lastQKey = sig;
  const el = $('q-list');
  if (!d.queue || !d.queue.length) {
    el.innerHTML = '<div class="empty">Queue is empty</div>';
    return;
  }
  el.innerHTML = d.queue.map(t =>
    '<div class="q-row" onclick="cmd(\'play_queue\',' + t.index + ')">' +
      '<div class="q-info"><div class="q-title">' + esc(t.name) + '</div><div class="q-sub">' + esc(t.artists) + '</div></div>' +
      '<button class="q-del" aria-label="Remove" onclick="event.stopPropagation();cmd(\'remove_queue\',' + t.index + ')">' + svg(I.del) + '</button>' +
    '</div>').join('');
}
$('seek').addEventListener('input', () => { seeking = true; $('pos').textContent = fmt($('seek').value); });
$('seek').addEventListener('change', () => { cmd('seek', +$('seek').value); seeking = false; });
$('vol').addEventListener('input', () => { voling = true; cmd('volume', +$('vol').value); });
$('vol').addEventListener('change', () => { voling = false; });
const poll = () => fetch(api('/api/state')).then(r => r.ok ? r.json() : null).then(d => d && paint(d)).catch(() => {});
const pollLyrics = () => fetch(api('/api/lyrics')).then(r => r.ok ? r.json() : null).then(d => d && paintLyrics(d)).catch(() => {});
const pollQueue = () => fetch(api('/api/queue')).then(r => r.ok ? r.json() : null).then(d => d && paintQueue(d)).catch(() => {});
poll();
setInterval(() => { poll(); if (tab === 'lyrics') pollLyrics(); if (tab === 'queue') pollQueue(); }, 900);
</script>
</body>
</html>
"""
