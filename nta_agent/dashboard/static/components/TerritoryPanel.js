import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, onMounted, onUnmounted } = window.Vue;
const MAPW = 600;
const STEPS = [1, 2, 5, 10, 20, 25, 50, 100];
const ML = 28, MT = 18;   // ruler margins

function labelStep(scale){ for(const s of STEPS){ if(s*scale >= 56) return s; } return 100; }

export default {
 setup(){
  const canvas=ref(null), tip=ref(null), sel=ref(null);
  let scale=16, originX=0, originY=0, fitted=false, hover=null;
  let data={main:0, mw:MAPW, owned:[], accepted:[], forts:[], garr:[], recs:[]};
  let stateMap=new Map();
  let dragging=false, moved=0, lastX=0, lastY=0;

  const rowOf=(y)=> (data.mw-1) - y;
  const sX=(x)=> originX + x*scale;
  const sY=(y)=> originY + rowOf(y)*scale;
  const idx=(x,y)=> y*data.mw + x;
  const cellAt=(px,py)=>({ x: Math.floor((px-originX)/scale),
                           y: (data.mw-1) - Math.floor((py-originY)/scale) });

  function buildStateMap(){
   stateMap=new Map();
   const put=(x,y,label,index)=>{ const k=idx(x,y); if(!stateMap.has(k)) stateMap.set(k,{label,index:index??k}); };
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw);
   [[mx,my],[mx+1,my],[mx,my+1],[mx+1,my+1]].forEach(([x,y])=>put(x,y,"thành chính"));
   data.forts.forEach(([x,y])=>put(x,y,"Cứ Điểm"));
   data.accepted.forEach(([x,y])=>put(x,y,"dự kiến xây"));
   data.recs.forEach(r=>put(r.x,r.y,"gợi ý",r.index));
   data.garr.forEach(([x,y])=>put(x,y,"quân trú"));
   data.owned.forEach(([x,y])=>put(x,y,"đã chiếm"));
  }

  function fitView(cv){
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw), R=6;
   const pts=[[mx,my],...data.owned,...data.accepted,...data.forts,...data.garr,
              ...data.recs.map(r=>[r.x,r.y]),[mx-R,my-R],[mx+1+R,my+1+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   scale=Math.max(6, Math.min(60, Math.floor(Math.min((cv.width-ML)/cols,(cv.height-MT)/rows))));
   originX = ML + Math.floor((cv.width-ML - cols*scale)/2) - minX*scale;
   originY = MT + Math.floor((cv.height-MT - rows*scale)/2) - rowOf(maxY)*scale;
  }
  function recenter(cv){ scale=16;
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw);  // 2x2 block center
   originX = cv.width/2 - (mx+0.5)*scale;
   originY = cv.height/2 - rowOf(my+0.5)*scale; }
  function zoomAt(px,py,f){ const s2=Math.max(6, Math.min(60, scale*f));
   originX = px-(px-originX)*s2/scale; originY = py-(py-originY)*s2/scale; scale=s2; render(); }

  function render(){
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height;
   ctx.fillStyle="#0b1320"; ctx.fillRect(0,0,W,H);
   if(!data.main){ ctx.fillStyle="#8b949e"; ctx.font="12px system-ui";
    ctx.fillText("Chưa có dữ liệu bản đồ.", ML+8, MT+20); return; }
   const x0=Math.max(0,Math.floor((ML-originX)/scale)), x1=Math.min(data.mw-1,Math.ceil((W-originX)/scale));
   const rTop=Math.max(0,Math.floor((MT-originY)/scale)), rBot=Math.min(data.mw-1,Math.ceil((H-originY)/scale));
   const yHi=(data.mw-1)-rTop, yLo=(data.mw-1)-rBot;
   const inView=(x,y)=> x>=x0&&x<=x1&&y>=yLo&&y<=yHi;
   ctx.save(); ctx.beginPath(); ctx.rect(ML,MT,W-ML,H-MT); ctx.clip();
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(sX(x)+1,sY(y)+1,scale-2,scale-2); };
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw), R=6;
   // speed zone: Manhattan distance <= 6 from the 2x2 city block (diagonal costs
   // 2) -> a rotated diamond / octagon, NOT an axis-aligned square.
   const bx0=mx, bx1=mx+1, by0=my, by1=my+1;
   // vertices on CELL EDGES/CORNERS (outer edges of the boundary cells) so the
   // dashed diamond hugs the grid; diagonal facets are 45° lines through corners.
   const Lx=x=>sX(x), Rx=x=>sX(x)+scale, Ty=y=>sY(y), By=y=>sY(y)+scale;
   const zoneV=[[Rx(bx1+R),By(by0)],[Rx(bx1+R),Ty(by1)],
                [Rx(bx1),Ty(by1+R)],[Lx(bx0),Ty(by1+R)],
                [Lx(bx0-R),Ty(by1)],[Lx(bx0-R),By(by0)],
                [Lx(bx0),By(by0-R)],[Rx(bx1),By(by0-R)]];
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]); ctx.beginPath();
   zoneV.forEach((v,i)=>{ if(i===0) ctx.moveTo(v[0],v[1]); else ctx.lineTo(v[0],v[1]); });
   ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
   data.owned.forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#199e70"); });
   ctx.strokeStyle="#c3c2b7"; ctx.lineWidth=1.5;
   data.garr.forEach(([x,y])=>{ if(inView(x,y)) ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); });
   data.forts.forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#d95926"); });
   data.accepted.forEach(([x,y])=>{ if(inView(x,y)){ box(x,y,"#d95926");
    ctx.fillStyle="#0b1320"; ctx.beginPath(); ctx.arc(sX(x)+scale/2,sY(y)+scale/2,Math.max(1.5,scale/6),0,7); ctx.fill(); } });
   data.recs.forEach(r=>{ if(inView(r.x,r.y)){ ctx.strokeStyle="#e66767"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(sX(r.x)+scale/2,sY(r.y)+scale/2,Math.max(3,scale/2-1),0,7); ctx.stroke(); } });
   [[mx,my],[mx+1,my],[mx,my+1],[mx+1,my+1]].forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#3987e5"); });
   if(hover && inView(hover.x,hover.y)){ ctx.strokeStyle="#58a6ff"; ctx.lineWidth=2;
    ctx.strokeRect(sX(hover.x)+1,sY(hover.y)+1,scale-2,scale-2); }
   ctx.restore();
   ctx.fillStyle="#0b1320"; ctx.fillRect(0,0,W,MT); ctx.fillRect(0,0,ML,H);
   ctx.fillStyle="#8b949e"; ctx.font="10px ui-monospace,Consolas,monospace";
   const step=labelStep(scale);
   ctx.textAlign="center"; ctx.textBaseline="alphabetic";
   for(let x=x0; x<=x1; x++){ if(x%step===0){ const px=sX(x)+scale/2; if(px>=ML) ctx.fillText(String(x), px, MT-4); } }
   ctx.textAlign="right"; ctx.textBaseline="middle";
   for(let y=yLo; y<=yHi; y++){ if(y%step===0){ const py=sY(y)+scale/2; if(py>=MT) ctx.fillText(String(y), ML-4, py); } }
  }

  async function load(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   const mw=t.map_width||MAPW;
   data={ main:t.main_city||0, mw, owned:f.owned_cells||[], accepted:f.accepted||[],
    forts:(t.forts||[]).map(x=>[x.x,x.y]),
    garr:(t.garrisons||[]).map(i=>[i%mw, Math.floor(i/mw)]),
    recs:f.recommendations||[] };
   buildStateMap();
   const cv=canvas.value;
   if(cv && data.main && !fitted){ fitView(cv); fitted=true; }
   render();
  }
  usePolling(load, 4000);

  const toCanvas=(ev)=>{ const cv=canvas.value, r=cv.getBoundingClientRect();
   return [ (ev.clientX-r.left)*(cv.width/r.width), (ev.clientY-r.top)*(cv.height/r.height) ]; };
  function onDown(ev){ dragging=true; moved=0; lastX=ev.clientX; lastY=ev.clientY; }
  function onMove(ev){
   const cv=canvas.value, r=cv.getBoundingClientRect();
   if(dragging){ const dx=ev.clientX-lastX, dy=ev.clientY-lastY; moved+=Math.abs(dx)+Math.abs(dy);
    originX += dx*(cv.width/r.width); originY += dy*(cv.height/r.height);
    lastX=ev.clientX; lastY=ev.clientY; render(); return; }
   const [px,py]=toCanvas(ev);
   if(px<ML||py<MT){ if(hover){hover=null;render();} tip.value=null; return; }
   const c=cellAt(px,py); hover=c;
   const st=stateMap.get(idx(c.x,c.y));
   tip.value={ left:(ev.clientX-r.left)+12, top:(ev.clientY-r.top)+12,
     text:`(${c.x}, ${c.y})`+(st?` · ${st.label}`:" · trống") };
   render();
  }
  function onUp(ev){ dragging=false;
   if(moved<4){ const [px,py]=toCanvas(ev);
    if(px>=ML&&py>=MT){ const c=cellAt(px,py), st=stateMap.get(idx(c.x,c.y));
     const r=canvas.value.getBoundingClientRect();
     sel.value={ x:c.x, y:c.y, index: st?st.index:idx(c.x,c.y), state: st?st.label:"trống",
       left:Math.min(ev.clientX-r.left, r.width-170), top:(ev.clientY-r.top) }; } } }
  function onLeave(){ hover=null; tip.value=null; render(); }
  function onWheel(ev){ ev.preventDefault(); const [px,py]=toCanvas(ev); zoomAt(px,py, ev.deltaY<0?1.15:1/1.15); }
  function zoomBtn(f){ const cv=canvas.value; zoomAt(cv.width/2, cv.height/2, f); }
  function recenterBtn(){ recenter(canvas.value); render(); }
  function fitBtn(){ fitView(canvas.value); render(); }
  async function decide(decision){ if(!sel.value) return;
   await postJSON("/api/forts/decide",{index:sel.value.index,decision}); sel.value=null; load(); }

  onMounted(()=>{ const cv=canvas.value; if(cv) cv.addEventListener("wheel", onWheel, {passive:false}); });
  onUnmounted(()=>{ const cv=canvas.value; if(cv) cv.removeEventListener("wheel", onWheel); });

  return { canvas, tip, sel, onDown, onMove, onUp, onLeave, zoomBtn, recenterBtn, fitBtn, decide };
 },
 template:`<div class="card full"><h2>Lãnh thổ</h2>
  <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
   <button @click="zoomBtn(1.25)">＋</button><button @click="zoomBtn(0.8)">－</button>
   <button @click="fitBtn">Vừa khung</button><button @click="recenterBtn">Về thành chính</button>
   <span class="muted" style="font-size:12px">Kéo để di chuyển · cuộn để phóng to · bấm ô để xem toạ độ</span></div>
  <div style="position:relative">
   <canvas ref="canvas" class="terrmap" width="640" height="360"
     @mousedown="onDown" @mousemove="onMove" @mouseup="onUp" @mouseleave="onLeave"
     style="cursor:grab"></canvas>
   <div v-if="tip" class="muted" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
     border-radius:4px;padding:2px 6px;font-size:11px;pointer-events:none;z-index:6"
     :style="{left:tip.left+'px',top:tip.top+'px'}">{{ tip.text }}</div>
   <div v-if="sel" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
     border-radius:6px;padding:6px 8px;z-index:7" :style="{left:sel.left+'px',top:(sel.top+16)+'px'}">
    <div class="muted" style="font-size:12px">Ô ({{ sel.x }}, {{ sel.y }}) · {{ sel.state }}</div>
    <template v-if="sel.state==='gợi ý'">
     <button @click="decide('accept')">✓ Chấp thuận</button>
     <button @click="decide('reject')">✕ Từ chối</button></template>
    <button @click="sel=null">Đóng</button></div>
  </div>
  <div class="muted" style="margin-top:6px;font-size:12px;display:flex;gap:12px;flex-wrap:wrap">
   <span><b style="color:#3987e5">■</b> thành chính</span>
   <span><b style="color:#199e70">■</b> ô đã chiếm</span>
   <span><b style="color:#d95926">■</b> Cứ Điểm / dự kiến</span>
   <span><b style="color:#e66767">◯</b> gợi ý</span>
   <span><b style="color:#c3c2b7">▢</b> quân trú</span>
   <span><b style="color:#3b6ea5">◇</b> vùng thoi nét đứt = bán kính 6 ô quanh thành 2×2 (Manhattan, đi chéo tốn 2 — đã tăng tốc, không cần xây Cứ Điểm bên trong)</span>
  </div></div>`
};
