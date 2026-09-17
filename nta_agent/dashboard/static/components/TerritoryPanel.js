import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const idxXY=(i,mw)=>[i%mw, Math.floor(i/mw)];
export default {
 setup(){
  const canvas=ref(null), summary=ref("—"), legend=ref("");
  async function draw(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   const forts=(t.forts||[]);
   summary.value=`Thành chính: ${t.main_city||"?"} · Quân trú: ${(t.garrisons||[]).length}`;
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height; ctx.clearRect(0,0,W,H);
   const mw=t.map_width||600, main=t.main_city||0;
   if(!main){ legend.value="Chưa có dữ liệu bản đồ."; return; }
   const [mx,my]=idxXY(main,mw);
   const owned=f.owned_cells||[];
   const fpts=forts.map(x=>[x.x,x.y]);
   const garr=(t.garrisons||[]).map(i=>idxXY(i,mw));
   const recs=(f.recommendations||[]).map(r=>[r.x,r.y]);
   const R=6;
   const pts=[[mx,my],...owned,...fpts,...garr,...recs,[mx-R,my-R],[mx+R,my+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   const cell=Math.max(3,Math.floor(Math.min(W/cols,H/rows)));
   const ox=Math.floor((W-cols*cell)/2), oy=Math.floor((H-rows*cell)/2);
   const gx=x=>ox+(x-minX)*cell, gy=y=>oy+(y-minY)*cell;
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(gx(x)+1,gy(y)+1,cell-2,cell-2); };
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
   ctx.strokeRect(gx(mx-R)+0.5,gy(my-R)+0.5,(2*R+1)*cell,(2*R+1)*cell); ctx.setLineDash([]);
   owned.forEach(([x,y])=>box(x,y,"#2e7d5b"));
   ctx.strokeStyle="#c9a227"; ctx.lineWidth=1.5;
   garr.forEach(([x,y])=>ctx.strokeRect(gx(x)+2,gy(y)+2,cell-4,cell-4));
   fpts.forEach(([x,y])=>box(x,y,"#e08a2b"));
   recs.forEach(([x,y])=>{ ctx.strokeStyle="#e5484d"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(3,cell/2-1),0,Math.PI*2); ctx.stroke(); });
   box(mx,my,"#3b82f6");
   legend.value=`🟦 thành chính · 🟩 ô đã chiếm (${owned.length}) · 🟨 quân trú (${garr.length}) · `
    +`🟧 Cứ Điểm (${fpts.length}) · 🔴 gợi ý (${recs.length}) · ⬚ nét đứt = bán kính ${R} ô (đã tăng tốc)`;
  }
  usePolling(draw, 4000);
  return { canvas, summary, legend };
 },
 template:`<div class="card full"><h2>Lãnh thổ</h2>
  <div class="muted">{{ summary }}</div>
  <canvas ref="canvas" class="terrmap" width="640" height="360"></canvas>
  <div class="muted" style="margin-top:6px;font-size:12px">{{ legend }}</div></div>`
};
