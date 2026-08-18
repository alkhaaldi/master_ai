/* ═══ Master AI — Shared Bottom Navigation ═══ */
(function(){
"use strict";

const NAV_ITEMS = [
  {icon:"\u{1F3E0}",label:"\u0627\u0644\u0631\u0626\u064A\u0633\u064A\u0629",path:"/trading/home"},
  {icon:"\u{1F4C8}",label:"\u0633\u0648\u064A\u0646\u0642",path:"/trading/swing"},
  {icon:"\u{1F4E1}",label:"\u0627\u0644\u0631\u0627\u062F\u0627\u0631",path:"/trading/radar"},
  {icon:"\u{1F4CA}",label:"\u0625\u0634\u0627\u0631\u0627\u062A",path:"/trading/signals"},
  {icon:"\u{1F4BC}",label:"\u0627\u0644\u0645\u0631\u0627\u0643\u0632",path:"/trading/positions"},
  {icon:"\u{1F9E0}",label:"\u0627\u0644\u0639\u0642\u0644",path:"/trading/brain"},
  {icon:"\u2699\uFE0F",label:"\u0627\u0644\u0646\u0638\u0627\u0645",path:"/trading/system"},
];

const MORE_ITEMS = [
  {icon:"\u{1F4D3}",label:"\u0627\u0644\u064A\u0648\u0645\u064A\u0629",path:"/trading/journal"},
  {icon:"\u{1F4C5}",label:"\u0627\u0644\u0645\u0648\u0627\u0639\u064A\u062F",path:"/trading/calendar"},
  {icon:"\u{1F916}",label:"\u0627\u0644\u0645\u0633\u0627\u0639\u062F",path:"/trading/assistant"},
  {icon:"\u{1F3E0}",label:"\u0627\u0644\u0628\u064A\u062A",path:"/trading/home-control"},
  {icon:"\u{1F4D0}",label:"\u0627\u0644\u062A\u062D\u0644\u064A\u0644",path:"/trading/analysis"},
  {icon:"\u{1F52E}",label:"\u0642\u0631\u0627\u0631\u0627\u062A",path:"/trading/decisions"},
];

/* Detect current page */
const currentPath = window.location.pathname.replace(/\.html$/,'').replace(/\/$/,'');

function isActive(path){
  return currentPath === path || currentPath === path + '.html';
}

/* Build CSS */
const style = document.createElement('style');
style.textContent = `
.mnav{position:fixed;bottom:0;left:0;right:0;z-index:9999;background:rgba(12,21,37,.96);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-top:1px solid rgba(198,151,75,.15);padding:4px 4px calc(4px + env(safe-area-inset-bottom,0px));display:flex;justify-content:space-around;align-items:flex-start;gap:0}
.mnav-item{display:flex;flex-direction:column;align-items:center;gap:1px;padding:4px 2px;border-radius:8px;cursor:pointer;text-decoration:none;min-width:0;flex:1;transition:all .15s ease;-webkit-tap-highlight-color:transparent;border:1px solid transparent}
.mnav-item:active{transform:scale(.92)}
.mnav-item .mnav-icon{font-size:1.15rem;line-height:1.2}
.mnav-item .mnav-label{font-family:'Tajawal','Noto Kufi Arabic',sans-serif;font-size:.52rem;font-weight:600;color:#6B7D90;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.mnav-item.active .mnav-label{color:#C6974B}
.mnav-item.active{background:rgba(198,151,75,.08);border-color:rgba(198,151,75,.15)}
.mnav-more{position:relative}
.mnav-more-panel{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:rgba(14,25,41,.97);backdrop-filter:blur(20px);border:1px solid rgba(198,151,75,.2);border-radius:12px;padding:8px;width:max-content;max-width:85vw;box-shadow:0 -8px 32px rgba(0,0,0,.5);z-index:10000}
.mnav-more-panel.show{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}
.mnav-more-item{display:flex;flex-direction:column;align-items:center;gap:2px;padding:10px 8px;border-radius:8px;cursor:pointer;text-decoration:none;transition:all .15s;border:1px solid transparent}
.mnav-more-item:active{background:rgba(198,151,75,.12)}
.mnav-more-item.active{background:rgba(198,151,75,.08);border-color:rgba(198,151,75,.15)}
.mnav-more-item .mnav-icon{font-size:1.1rem}
.mnav-more-item .mnav-label{font-family:'Tajawal',sans-serif;font-size:.55rem;color:#6B7D90;white-space:nowrap}
.mnav-more-item.active .mnav-label{color:#C6974B}
.mnav-overlay{display:none;position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,.4)}
.mnav-overlay.show{display:block}
`;
document.head.appendChild(style);

/* Build overlay */
const overlay = document.createElement('div');
overlay.className = 'mnav-overlay';
overlay.onclick = () => closeMore();
document.body.appendChild(overlay);

/* Build navbar */
const nav = document.createElement('nav');
nav.className = 'mnav';

NAV_ITEMS.forEach(item => {
  const a = document.createElement('a');
  a.className = 'mnav-item' + (isActive(item.path) ? ' active' : '');
  a.href = item.path;
  a.innerHTML = '<span class="mnav-icon">' + item.icon + '</span><span class="mnav-label">' + item.label + '</span>';
  nav.appendChild(a);
});

/* More button */
const moreActive = MORE_ITEMS.some(i => isActive(i.path));
const moreBtn = document.createElement('div');
moreBtn.className = 'mnav-item mnav-more' + (moreActive ? ' active' : '');
moreBtn.innerHTML = '<span class="mnav-icon">\u2022\u2022\u2022</span><span class="mnav-label">\u0627\u0644\u0645\u0632\u064A\u062F</span>';
moreBtn.onclick = toggleMore;

/* More panel */
const panel = document.createElement('div');
panel.className = 'mnav-more-panel';
MORE_ITEMS.forEach(item => {
  const a = document.createElement('a');
  a.className = 'mnav-more-item' + (isActive(item.path) ? ' active' : '');
  a.href = item.path;
  a.innerHTML = '<span class="mnav-icon">' + item.icon + '</span><span class="mnav-label">' + item.label + '</span>';
  panel.appendChild(a);
});
moreBtn.appendChild(panel);
nav.appendChild(moreBtn);
document.body.appendChild(nav);

/* Adjust body padding for navbar */
document.body.style.paddingBottom = '70px';

function toggleMore(e){
  e.stopPropagation();
  const isOpen = panel.classList.contains('show');
  if(isOpen) closeMore(); else openMore();
}
function openMore(){
  panel.classList.add('show');
  overlay.classList.add('show');
}
function closeMore(){
  panel.classList.remove('show');
  overlay.classList.remove('show');
}

})();
