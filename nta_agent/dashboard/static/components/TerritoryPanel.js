import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const idxXY=(i,mw)=>[i%mw, Math.floor(i/mw)];
const ML=26, MT=16;  // left/top margins reserved for rulers
export default {
 setup(){
  const canvas=ref(null), summary=ref("—"), legend=ref("");
  const geom=ref(null);            // {minX,minY,cell,ox,oy} for hit-testing
  const recs=ref([]);              // pending recs [{index,x,y,reason}]
  const sel=ref(null);             // selected rec + popover position
  async function draw(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   recs.value=f.recommendations||[];
   summary.value=`Thành chính: ${t.main_city||"?"} · Quân trú: ${(t.garrisons||[]).length}`;
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height; ctx.clearRect(0,0,W,H);
   const mw=t.map_width||600, main=t.main_city||0;
   if(!main){ legend.value="Chưa có dữ liệu bản đồ."; geom.value=null; return; }
   const [mx,my]=idxXY(main,mw);
   const owned=f.owned_cells||[];
   const accepted=f.accepted||[];
   const fpts=(t.forts||[]).map(x=>[x.x,x.y]);
   const garr=(t.garrisons||[]).map(i=>idxXY(i,mw));
   const rpts=recs.value.map(r=>[r.x,r.y]);
   const R=6;
   const pts=[[mx,my],...owned,...accepted,...fpts,...garr,...rpts,[mx-R,my-R],[mx+R,my+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   const cell=Math.max(3,Math.floor(Math.min((W-ML)/cols,(H-MT)/rows)));
   const ox=ML+Math.floor((W-ML-cols*cell)/2), oy=MT+Math.floor((H-MT-rows*cell)/2);
   geom.value={minX,minY,cell,ox,oy};
   const gx=x=>ox+(x-minX)*cell, gy=y=>oy+(y-minY)*cell;
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(gx(x)+1,gy(y)+1,cell-2,cell-2); };
   // rulers: adaptive step so labels are ~>=34px apart
   const step=Math.max(1,Math.ceil(34/cell));
   ctx.fillStyle="#8b949e"; ctx.font="10px ui-monospace,Consolas,monospace";
   ctx.textAlign="center"; ctx.textBaseline="alphabetic";
   for(let x=minX; x<=maxX; x++){ if((x-minX)%step===0) ctx.fillText(String(x), gx(x)+cell/2, MT-4); }
   ctx.textAlign="right"; ctx.textBaseline="middle";
   for(let y=minY; y<=maxY; y++){ if((y-minY)%step===0) ctx.fillText(String(y), ML-4, gy(y)+cell/2); }
   // radius-6 zone
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
   ctx.strokeRect(gx(mx-R)+0.5,gy(my-R)+0.5,(2*R+1)*cell,(2*R+1)*cell); ctx.setLineDash([]);
   owned.forEach(([x,y])=>box(x,y,"#2e7d5b"));
   ctx.strokeStyle="#c9a227"; ctx.lineWidth=1.5;
   garr.forEach(([x,y])=>ctx.strokeRect(gx(x)+2,gy(y)+2,cell-4,cell-4));
   fpts.forEach(([x,y])=>box(x,y,"#e08a2b"));
   // accepted (planned forts): orange fill + a dark check dot
   accepted.forEach(([x,y])=>{ box(x,y,"#e08a2b");
    ctx.fillStyle="#0b1320"; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(1.5,cell/6),0,Math.PI*2); ctx.fill(); });
   // pending recs: red ring (clickable)
   rpts.forEach(([x,y])=>{ ctx.strokeStyle="#e5484d"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(3,cell/2-1),0,Math.PI*2); ctx.stroke(); });
   box(mx,my,"#3b82f6");
   legend.value=`🟦 thành chính · 🟩 ô đã chiếm (${owned.length}) · 🟨 quân trú (${garr.length}) · `
    +`🟧 Cứ Điểm/dự kiến (${fpts.length+accepted.length}) · 🔴 gợi ý (${rpts.length}) · ⬚ bán kính ${R} ô`;
  }
  function onClick(ev){
   const g=geom.value; if(!g) return;
   const cv=canvas.value, rect=cv.getBoundingClientRect();
   const px=(ev.clientX-rect.left)*(cv.width/rect.width);
   const py=(ev.clientY-rect.top)*(cv.height/rect.height);
   const cx=Math.round((px-g.ox)/g.cell)+g.minX, cy=Math.round((py-g.oy)/g.cell)+g.minY;
   const hit=recs.value.find(r=>r.x===cx && r.y===cy);
   sel.value = hit ? {index:hit.index,x:hit.x,y:hit.y,
     left:Math.min(ev.clientX-rect.left, cv.width-150), top:ev.clientY-rect.top} : null;
  }
  async function decide(decision){
   if(!sel.value) return;
   await postJSON("/api/forts/decide",{index:sel.value.index,decision});
   sel.value=null; draw();
  }
  usePolling(draw, 4000);
  return { canvas, summary, legend, sel, onClick, decide };
 },
 template:`<div class="card full" style="position:relative"><h2>Lãnh thổ</h2>
  <div class="muted">{{ summary }}</div>
  <canvas ref="canvas" class="terrmap" width="640" height="360" @click="onClick"></canvas>
  <div v-if="sel" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
    border-radius:6px;padding:6px 8px;z-index:5" :style="{left:sel.left+'px',top:(sel.top+40)+'px'}">
   <div class="muted" style="font-size:12px">Gợi ý Cứ Điểm ({{ sel.x }},{{ sel.y }})</div>
   <button @click="decide('accept')">✓ Chấp thuận</button>
   <button @click="decide('reject')">✕ Từ chối</button>
   <button @click="sel=null">Đóng</button></div>
  <div class="muted" style="margin-top:6px;font-size:12px">{{ legend }}</div></div>`
};
