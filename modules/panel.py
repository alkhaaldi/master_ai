"""Master AI - Web Panel Module."""
import os
from fastapi import Query
from fastapi.responses import HTMLResponse

MASTER_API_KEY = os.getenv("MASTER_AI_API_KEY", "")

_PANEL_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Master AI Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;font-size:14px;padding:16px}
h1{color:#58a6ff;font-size:20px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
h1 .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;max-height:440px;overflow-y:auto}
.card h2{color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;position:sticky;top:0;background:#161b22;padding-bottom:4px}
.card.full{grid-column:1/-1}
.it{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px}
.it .m{color:#8b949e;font-size:11px;margin-top:3px}
.b{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600}
.b.low{background:#238636;color:#fff}.b.medium{background:#d29922;color:#000}.b.high{background:#da3633;color:#fff}
.b.fact{background:#1f6feb;color:#fff}.b.context{background:#8957e5;color:#fff}.b.pattern{background:#d29922;color:#000}
.b.operational_policy{background:#da3633;color:#fff}.b.preference{background:#238636;color:#fff}
.bt{border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;margin-right:4px;margin-top:6px}
.bt.ap{background:#238636;color:#fff}.bt.ap:hover{background:#2ea043}
.bt.dn{background:#da3633;color:#fff}.bt.dn:hover{background:#f85149}
.bt:disabled{opacity:.4;cursor:not-allowed}
.em{color:#484f58;font-style:italic;padding:16px;text-align:center}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
#st{color:#484f58;font-size:11px}
</style></head><body>
<div class="bar"><h1><span class="dot"></span>Master AI Panel</h1><span id="st">loading...</span></div>
<div class="grid">
<div class="card full"><h2 id="ah">Pending Approvals</h2><div id="ap">loading...</div></div>
<div class="card"><h2>Recent Memory</h2><div id="me">loading...</div></div>
<div class="card"><h2>Recent Events</h2><div id="ev">loading...</div></div>
</div>
<script>
const K=new URLSearchParams(location.search).get('key')||'';
const H={'X-API-Key':K};
const $=id=>document.getElementById(id);
function x(s){if(!s)return'';const d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
function ago(t){if(!t)return'';const d=Date.now()-new Date(t).getTime();if(d<0)return'future';if(d<60e3)return(d/1e3|0)+'s';if(d<36e5)return(d/6e4|0)+'m';if(d<864e5)return(d/36e5|0)+'h';return(d/864e5|0)+'d'}
function b(c){return'<span class="b '+x(c)+'">'+x(c)+'</span>'}

async function F(p,o){try{const r=await fetch(p,Object.assign({headers:H},o||{}));return r.ok?r.json():null}catch(e){return null}}

document.addEventListener('click',async function(e){
 var t=e.target;if(!t.classList.contains('bt'))return;
 var id=t.getAttribute('data-i'),yes=t.getAttribute('data-a')==='1';
 if(!id)return;
 document.querySelectorAll('button[data-i="'+id+'"]').forEach(function(z){z.disabled=true});
 await F('/approve/'+id+'?action='+(yes?'approve':'deny'),{method:'POST'});
 R();
});

async function R(){
 var t=Date.now();
 var a=await F('/approvals/pending');
 if(a){
 $('ah').textContent='Pending Approvals ('+a.count+')';
 if(!a.count)$('ap').innerHTML='<div class="em">No pending approvals</div>';
 else $('ap').innerHTML=a.pending.map(function(i){
  var id=x(i.id||i.approval_id||'?');
  var tp=i.action_type||i.type||'?';
  var rk=i.risk_level||i.risk||'low';
  var dt=typeof i.description==='string'?i.description:(typeof i.args==='object'?JSON.stringify(i.args):'');
  return'<div class="it"><div>'+b(rk)+' <b>'+x(tp)+'</b> '+x(dt).substring(0,120)+'</div>'+
  '<div class="m">'+id+' · '+ago(i.created_at)+'</div>'+
  '<button class="bt ap" data-i="'+id+'" data-a="1">Approve</button>'+
  '<button class="bt dn" data-i="'+id+'" data-a="0">Deny</button></div>'
 }).join('');
 }
 var m=await F('/memory/recent?limit=10');
 if(m&&m.memories){
 if(!m.count)$('me').innerHTML='<div class="em">No memories</div>';
 else $('me').innerHTML=m.memories.map(function(i){
  return'<div class="it"><div>'+x((i.content||'').substring(0,140))+'</div>'+
  '<div class="m">'+b(i.type||'fact')+' '+x(i.category||'')+' · '+ago(i.created_at)+'</div></div>'
 }).join('');
 }
 var e=await F('/events?limit=10');
 if(e&&e.events){
 if(!e.events.length)$('ev').innerHTML='<div class="em">No events</div>';
 else $('ev').innerHTML=e.events.map(function(i){
  return'<div class="it"><div>'+b(i.risk||'low')+' <b>'+x(i.type||'?')+'</b> '+x(i.title||'')+'</div>'+
  '<div class="m">'+x(i.source||'')+' · '+x(i.user||'')+' · '+x(i.status||'')+' · '+ago(i.created_at)+'</div></div>'
 }).join('');
 }else{$('ev').innerHTML='<div class="em">Events endpoint unavailable</div>'}
 $('st').textContent=new Date().toLocaleTimeString()+' ('+(Date.now()-t)+'ms)';
}
if(!K){document.body.innerHTML='<h1 style="color:#da3633">Missing key</h1><p style="color:#8b949e;margin-top:8px">Use /panel?key=YOUR_API_KEY</p>'}
else{R();setInterval(R,10000)}
</script></body></html>"""


def register_panel_routes(app):
    @app.get("/panel", response_class=HTMLResponse, tags=["panel"])
    async def web_panel(key: str = Query(default="")):
        if key != MASTER_API_KEY:
            return HTMLResponse("<h1 style=\'color:#da3633;font-family:monospace;padding:40px\'>401 Unauthorized</h1>", status_code=401)
        return HTMLResponse(_PANEL_HTML)
