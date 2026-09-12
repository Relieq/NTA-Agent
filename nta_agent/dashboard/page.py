"""The single, self-contained dashboard HTML page (inline CSS + JS)."""

INDEX_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NTA Agent</title>
<style>
 body{margin:0;font:14px system-ui,Segoe UI,Arial;background:#0f1216;color:#e6e6e6}
 header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#171b21;border-bottom:1px solid #262c34}
 h1{font-size:16px;margin:0}
 .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#666}
 .dot.on{background:#3fb950}.dot.wait{background:#d29922}
 main{padding:16px;display:grid;gap:12px;grid-template-columns:1fr 1fr;max-width:960px}
 .card{background:#171b21;border:1px solid #262c34;border-radius:8px;padding:12px}
 .card h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#8b949e;margin:0 0 8px}
 .kv{display:flex;flex-wrap:wrap;gap:8px 16px}.kv b{color:#fff}
 .full{grid-column:1/-1}
 ul{list-style:none;margin:0;padding:0}li{padding:3px 0;border-bottom:1px solid #21262d}
 .feed{max-height:320px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px}
 .muted{color:#8b949e}
</style></head><body>
<header><h1>NTA Agent</h1><div id="status"><span class="dot"></span><span id="statusText">…</span></div></header>
<main>
 <div class="card"><h2>Tài nguyên</h2><div id="res" class="kv"></div></div>
 <div class="card"><h2>Thành chính &amp; công trình</h2><div id="city"></div></div>
 <div class="card"><h2>Quân &amp; nhiệm vụ</h2><div id="misc"></div></div>
 <div class="card full"><h2>Quyết định đang chờ</h2><div id="decisions"><span class="muted">—</span></div></div>
 <div class="card full"><h2>Trang bị lính</h2><div id="equipment"><span class="muted">—</span></div></div>
 <div class="card full"><h2>Sự kiện gần đây</h2><ul id="feed" class="feed"></ul></div>
</main>
<script>
const RES=[["cereal","Lương"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],["gold","Vàng"],["stamina","Thể lực"]];
function ago(ts){if(!ts)return"";const s=Math.max(0,Math.round(Date.now()/1000-ts));return s+"s trước";}
function hms(ts){const d=new Date((ts||0)*1000);return d.toLocaleTimeString();}
async function j(u){try{const r=await fetch(u);return await r.json();}catch(e){return null;}}
async function post(cmd){try{await fetch("/api/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cmd)});}catch(e){}}
function decCard(d){
 const opts=(d.options||[]).map(o=>`<button data-a=select data-t="${d.track}" data-lv="${d.lv}" data-id="${o.ceri_id}">${o.name}</button>`).join(" ");
 const reroll=`<button data-a=reroll data-t="${d.track}" data-lv="${d.lv}">Làm mới${d.reset_count?(" ("+d.reset_count+")"):" (free)"}</button>`;
 return `<div style="margin:6px 0"><span class=muted>${d.track} · Lv${d.lv}</span><br>${opts} ${reroll}</div>`;
}
async function renderDecisions(){
 const ds=await j("/api/decisions")||[];
 const box=document.getElementById("decisions");
 box.innerHTML=ds.length?ds.map(decCard).join(""):"<span class=muted>—</span>";
 box.querySelectorAll("button").forEach(b=>b.onclick=async()=>{
   const cmd={action:b.dataset.a,track:b.dataset.t,lv:Number(b.dataset.lv)};
   if(b.dataset.a==="select")cmd.ceri_id=Number(b.dataset.id);
   b.disabled=true;b.textContent="đã gửi…";await post(cmd);
 });
}
function equipRow(p){
 const opts=(p.options||[]).map(o=>`<button data-p="${p.pawn_id}" data-u="${o.uid}" data-sk="${p.skin_id}" data-as="${p.attack_speed}"${o.uid===p.current_equip_uid?" disabled":""}>${o.name}</button>`).join(" ");
 return `<div style="margin:6px 0"><span class=muted>${p.pawn_name}</span> — hiện: <b>${p.current_equip_name||"—"}</b><br>${opts||"<span class=muted>không có trang bị phù hợp</span>"}</div>`;
}
async function renderEquipment(){
 const ps=await j("/api/equipment")||[];
 const box=document.getElementById("equipment");
 box.innerHTML=ps.length?ps.map(equipRow).join(""):"<span class=muted>—</span>";
 box.querySelectorAll("button").forEach(b=>b.onclick=async()=>{
   const cmd={action:"equip",pawn_id:Number(b.dataset.p),equip_uid:b.dataset.u,
              skin_id:Number(b.dataset.sk),attack_speed:Number(b.dataset.as)};
   b.disabled=true;b.textContent="đã gửi…";await post(cmd);
 });
}
async function refresh(){
 const s=await j("/api/state");
 const dot=document.querySelector("#status .dot"),txt=document.getElementById("statusText");
 if(!s||!s.ok){dot.className="dot wait";txt.textContent="Đang chờ agent…";
   document.getElementById("res").innerHTML="";document.getElementById("city").innerHTML="";document.getElementById("misc").innerHTML="";}
 else{
   dot.className="dot on";txt.textContent="đang chạy · "+ago(s.updated_at);
   const r=s.resources||{};
   document.getElementById("res").innerHTML=RES.map(([k,l])=>`${l} <b>${r[k]??0}</b>`).join("");
   const builds=(s.builds||[]).map(b=>`<li>${b.name||("#"+b.id)} <b>Lv${b.lv}</b></li>`).join("")||"<li class=muted>—</li>";
   const q=s.build_queue?s.build_queue.length:0;
   document.getElementById("city").innerHTML=`<div class=muted>@${s.main_city_index||"?"} · hàng đợi ${q}/${s.build_queue_slots||0}</div><ul>${builds}</ul>`;
   const p=s.player||{};
   document.getElementById("misc").innerHTML=`<div class=kv>Đội hành quân <b>${s.marches??0}</b> · Ô đã biết <b>${s.areas??0}</b></div>`+
     `<div class=kv style=margin-top:8px>Guide <b>${p.guide_tasks??0}</b> · Other <b>${p.other_tasks??0}</b> · Today <b>${p.today_tasks??0}</b></div>`;
 }
 const ev=await j("/api/events?n=50")||[];
 document.getElementById("feed").innerHTML=ev.slice().reverse().map(e=>{
   const extra=e.kind==="tick"?("tick "+e.i+" · "+((e.fired||[]).join(", ")||"—")):(e.kind+(e.detail?(" · "+e.detail):""));
   return `<li><span class=muted>${hms(e.ts)}</span> ${extra}</li>`;}).join("")||"<li class=muted>—</li>";
 renderDecisions();
 renderEquipment();
}
refresh();setInterval(refresh,2000);
</script></body></html>"""
