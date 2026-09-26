import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, onMounted, onUnmounted } = window.Vue;
const MAPW = 600;
const STEPS = [1, 2, 5, 10, 20, 25, 50, 100];
const ML = 28, MT = 18;   // ruler margins

function labelStep(scale){ for(const s of STEPS){ if(s*scale >= 56) return s; } return 100; }
const DIG_STATE={previewing:"Đang tính đường…", preview:"Xem trước — chờ xác nhận", active:"Đang dig",
 waiting:"Đang chờ (ô chưa đánh nổi)", done:"Hoàn tất", failed:"Không dig được", cancelled:"Đã huỷ"};
const DIG_REASON={no_path:"không có đường (bị chặn, hoặc mọi lối đều sát địch)",
 blocked_by_hard:"mọi lối đều phải qua ô nhóm dig chưa thắng nổi trong giới hạn tổn thất — sẽ chờ hồi máu/mạnh lên rồi thử lại",
 target_unsafe:"ô đích đã có chủ hoặc sát địch", target_lost:"đích bị chiếm và quanh đó không còn ô an toàn",
 owned:"ô này đã là của bạn"};
function fmtDur(s){ s=Math.round(s||0); const h=Math.floor(s/3600), m=Math.round((s%3600)/60);
 return h? `${h} giờ ${m} phút` : `${m} phút`; }

export default {
 setup(){
  const canvas=ref(null), tip=ref(null), sel=ref(null);
  let scale=16, originX=0, originY=0, fitted=false, hover=null;
  let data={main:0, mw:MAPW, owned:[], accepted:[], forts:[], garr:[], zone:[], fortCount:0, fortCap:0, armyCells:{},
            building:[], pending:[], enemy:[], enemyCities:[], frontier:[], ally:[], allyCities:[]};
  const dig=ref({state:"idle"});
  let digBuf=2; try{ const v=parseInt(localStorage.getItem("nta.digBuffer")); if(v>=0&&v<=6) digBuf=v; }catch(e){}
  const digBuffer=ref(digBuf);
  let stateMap=new Map(), zoneSet=new Set();
  let dragging=false, moved=0, lastX=0, lastY=0;

  const rowOf=(y)=> (data.mw-1) - y;
  const sX=(x)=> originX + x*scale;
  const sY=(y)=> originY + rowOf(y)*scale;
  const idx=(x,y)=> y*data.mw + x;
  // Convex hull (Andrew's monotone chain) over [x,y] points — used to draw the
  // territory boundary as a polygon connecting the outer boundary points.
  function convexHull(pts){
   if(pts.length<3) return pts.slice();
   pts=pts.slice().sort((a,b)=> a[0]-b[0] || a[1]-b[1]);
   const cr=(o,a,b)=> (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
   const lo=[]; for(const p of pts){ while(lo.length>=2 && cr(lo[lo.length-2],lo[lo.length-1],p)<=0) lo.pop(); lo.push(p); }
   const up=[]; for(let i=pts.length-1;i>=0;i--){ const p=pts[i]; while(up.length>=2 && cr(up[up.length-2],up[up.length-1],p)<=0) up.pop(); up.push(p); }
   lo.pop(); up.pop(); return lo.concat(up);
  }
  const cellAt=(px,py)=>({ x: Math.floor((px-originX)/scale),
                           y: (data.mw-1) - Math.floor((py-originY)/scale) });

  function buildStateMap(){
   stateMap=new Map();
   const put=(x,y,label,index)=>{ const k=idx(x,y); if(!stateMap.has(k)) stateMap.set(k,{label,index:index??k}); };
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw);
   [[mx,my],[mx+1,my],[mx,my+1],[mx+1,my+1]].forEach(([x,y])=>put(x,y,"thành chính"));
   data.forts.forEach(([x,y])=>put(x,y,"Cứ Điểm"));
   data.building.forEach(b=>put(b.x,b.y,"Cứ Điểm đang xây"));
   data.pending.forEach(p=>put(p.x,p.y,"Cứ Điểm chờ xây"));
   data.zone.forEach(([x,y])=>put(x,y,"gợi ý Cứ Điểm"));
   data.garr.forEach(([x,y])=>put(x,y,"quân trú"));
   data.owned.forEach(([x,y])=>put(x,y,"đã chiếm"));
   data.enemy.forEach(([x,y])=>put(x,y,"địch"));
   data.ally.forEach(([x,y])=>put(x,y,"đồng minh"));
   data.frontier.forEach(([x,y])=>put(x,y,"biên giới trống"));
  }

  function fitView(cv){
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw), R=6;
   // Fit to MY territory + speed zone only (enemies/frontier can be far/large;
   // they still render where they are — pan/zoom to see them).
   const pts=[[mx,my],...data.owned,...data.accepted,...data.forts,...data.garr,...data.frontier,
              ...data.zone,[mx-R,my-R],[mx+1+R,my+1+R]];
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
   // Protection/speed zone: cells within Manhattan distance <= 6 of the 2x2 city
   // block (diagonal costs 2). Rendered like the game's protect overlay (yellow
   // #F5E900): a light fill on in-zone cells + a crisp outline that follows the
   // CELL EDGES (staircase), never a diagonal cut across cells.
   const bx0=mx, bx1=mx+1, by0=my, by1=my+1;
   const inZone=(x,y)=>{ const dx=Math.max(bx0-x,0,x-bx1), dy=Math.max(by0-y,0,y-by1); return dx+dy<=R; };
   const zx0=Math.max(x0,bx0-R), zx1=Math.min(x1,bx1+R), zy0=Math.max(yLo,by0-R), zy1=Math.min(yHi,by1+R);
   ctx.fillStyle="rgba(245,233,0,0.10)";
   for(let y=zy0;y<=zy1;y++) for(let x=zx0;x<=zx1;x++) if(inZone(x,y)) ctx.fillRect(sX(x),sY(y),scale,scale);
   // "Bao chứa lãnh địa": the CONNECTED component of our owned cells that contains
   // the main city (4-connectivity). Cells reachable only through allied/other land
   // aren't our cells, so they naturally fall outside this component. Core cells are
   // solid green; owned-but-disconnected cells are drawn hollow/brown so they stand
   // out, and the component's bounding box is outlined.
   const core=(()=>{
    const own=new Set(data.owned.map(([x,y])=>x+","+y));
    const seeds=[[mx,my],[mx+1,my],[mx,my+1],[mx+1,my+1]];
    const s=new Set(); const q=[];
    for(const [x,y] of seeds){ const k=x+","+y; if(!s.has(k)){ s.add(k); q.push([x,y]); } }
    while(q.length){ const [x,y]=q.pop();
     for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){ const nx=x+dx,ny=y+dy,k=nx+","+ny;
      if(own.has(k)&&!s.has(k)){ s.add(k); q.push([nx,ny]); } } }
    return { set:s };
   })();
   data.owned.forEach(([x,y])=>{ if(!inView(x,y)) return;
    if(core.set.has(x+","+y)){ box(x,y,"#199e70"); }          // core (contiguous) territory
    else { box(x,y,"#5a4a2a");                                  // owned but disconnected
     ctx.strokeStyle="#e3b341"; ctx.lineWidth=1.5; ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); } });
   data.enemy.forEach(([x,y])=>{ if(inView(x,y)){ box(x,y,"#da3633");        // ô địch (đỏ)
    ctx.strokeStyle="#0b1320"; ctx.lineWidth=1; ctx.strokeRect(sX(x)+1.5,sY(y)+1.5,scale-3,scale-3); } });
   data.ally.forEach(([x,y])=>{ if(inView(x,y)){ box(x,y,"#2f81f7");        // ô đồng minh (lam)
    ctx.strokeStyle="#0b1320"; ctx.lineWidth=1; ctx.strokeRect(sX(x)+1.5,sY(y)+1.5,scale-3,scale-3); } });
   data.allyCities.forEach(c=>{ if(inView(c.x,c.y)){ ctx.strokeStyle="#cfe3ff"; ctx.lineWidth=2;
    ctx.strokeRect(sX(c.x)+3,sY(c.y)+3,scale-6,scale-6); } });             // thành đồng minh
   data.enemyCities.forEach(c=>{ if(inView(c.x,c.y)){ ctx.strokeStyle="#0b1320"; ctx.lineWidth=2;
    ctx.strokeRect(sX(c.x)+3,sY(c.y)+3,scale-6,scale-6); } });             // thành/fort địch
   // troop markers: ring coloured by activity + pawn-count badge (idle steel /
   // hành quân xanh / đang đánh đỏ). Drawn as a ring+halo'd number so it reads on
   // top of any cell fill (city, owned…), matching the in-game army overlay.
   const troopColor=(s)=> s===2?"#da3633" : s===1?"#58a6ff" : "#c3c2b7";
   Object.keys(data.armyCells).forEach(k=>{ const c=data.armyCells[k]; if(!inView(c.x,c.y)) return;
    const col=troopColor(c.maxState);
    ctx.strokeStyle=col; ctx.lineWidth=2; ctx.strokeRect(sX(c.x)+2,sY(c.y)+2,scale-4,scale-4);
    if(scale>=14){ const cx=sX(c.x)+scale/2, cy=sY(c.y)+scale/2;
     ctx.font="bold "+Math.min(13,scale-4)+"px system-ui"; ctx.textAlign="center"; ctx.textBaseline="middle";
     ctx.lineWidth=3; ctx.strokeStyle="#0b1320"; ctx.strokeText(String(c.pawns), cx, cy);
     ctx.fillStyle=col; ctx.fillText(String(c.pawns), cx, cy); } });
   data.accepted.forEach(([x,y])=>{ if(inView(x,y)){ box(x,y,"#d95926");
    ctx.fillStyle="#0b1320"; ctx.beginPath(); ctx.arc(sX(x)+scale/2,sY(y)+scale/2,Math.max(1.5,scale/6),0,7); ctx.fill(); } });
   ctx.strokeStyle="#8b949e"; ctx.lineWidth=1; ctx.setLineDash([2,2]);   // biên giới trống
   data.frontier.forEach(([x,y])=>{ if(inView(x,y)) ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); });
   ctx.setLineDash([]);
   // Recommended fort ZONE: a translucent orange fill + dotted outline on the
   // eligible owned cells; click one to build a Cứ Điểm there.
   ctx.fillStyle="rgba(217,89,38,0.22)";
   data.zone.forEach(([x,y])=>{ if(inView(x,y)) ctx.fillRect(sX(x)+1,sY(y)+1,scale-2,scale-2); });
   ctx.strokeStyle="#d95926"; ctx.lineWidth=1.5; ctx.setLineDash([3,2]);
   data.zone.forEach(([x,y])=>{ if(inView(x,y)) ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); });
   ctx.setLineDash([]);
   [[mx,my],[mx+1,my],[mx,my+1],[mx+1,my+1]].forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#3987e5"); });
   // Boundary of the contiguous territory: convex hull connecting the outer
   // boundary points (the 4 corners of every core cell), not an axis-aligned box.
   if(core.set.size){
    const pts=[];
    data.owned.forEach(([x,y])=>{ if(core.set.has(x+","+y)){
     pts.push([sX(x),sY(y)],[sX(x+1),sY(y)],[sX(x),sY(y)+scale],[sX(x+1),sY(y)+scale]); } });
    const h=convexHull(pts);
    if(h.length>=3){
     ctx.strokeStyle="#39d0d8"; ctx.lineWidth=2; ctx.setLineDash([6,4]);
     ctx.beginPath(); ctx.moveTo(h[0][0],h[0][1]);
     for(let i=1;i<h.length;i++) ctx.lineTo(h[i][0],h[i][1]);
     ctx.closePath(); ctx.stroke(); ctx.setLineDash([]); }
   }
   // zone outline along CELL EDGES (staircase): draw each in-zone cell's edges that
   // border an out-of-zone cell — matches the grid, no diagonal cut.
   ctx.strokeStyle="#F5E900"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]); ctx.beginPath();
   for(let y=zy0;y<=zy1;y++) for(let x=zx0;x<=zx1;x++){
    if(!inZone(x,y)) continue;
    if(!inZone(x+1,y)){ ctx.moveTo(sX(x)+scale,sY(y)); ctx.lineTo(sX(x)+scale,sY(y)+scale); }
    if(!inZone(x-1,y)){ ctx.moveTo(sX(x),sY(y)); ctx.lineTo(sX(x),sY(y)+scale); }
    if(!inZone(x,y+1)){ ctx.moveTo(sX(x),sY(y)); ctx.lineTo(sX(x)+scale,sY(y)); }
    if(!inZone(x,y-1)){ ctx.moveTo(sX(x),sY(y)+scale); ctx.lineTo(sX(x)+scale,sY(y)+scale); }
   }
   ctx.stroke(); ctx.setLineDash([]);
   // Built Cứ Điểm: a DISTINCT marker so it never blends into the orange
   // recommendation zone — purple fill + gold border + a 🏯 glyph (a small gold
   // pip when the cell is too tiny for a glyph). Drawn last so it sits on top.
   data.forts.forEach(([x,y])=>{ if(!inView(x,y)) return;
    box(x,y,"#8957e5");                                   // purple fill (distinct)
    ctx.strokeStyle="#f5b301"; ctx.lineWidth=2;           // gold border
    ctx.strokeRect(sX(x)+1.5,sY(y)+1.5,scale-3,scale-3);
    const cx=sX(x)+scale/2, cy=sY(y)+scale/2;
    if(scale>=16){ ctx.font=Math.min(scale-3,16)+"px system-ui";
     ctx.textAlign="center"; ctx.textBaseline="middle";
     ctx.lineWidth=3; ctx.strokeStyle="#0b1320"; ctx.strokeText("🏯", cx, cy);
     ctx.fillText("🏯", cx, cy); }
    else { ctx.fillStyle="#f5b301"; ctx.beginPath();
     ctx.arc(cx,cy,Math.max(1.5,scale/5),0,7); ctx.fill(); } });
   // Dig plan: orange path outline, planned Cứ Điểm (faded 🏯), hard cells (✕), target 🎯.
   const dg=dig.value||{};
   if(["preview","active","waiting","previewing"].includes(dg.state)){
    ctx.strokeStyle="#ff9f1c"; ctx.lineWidth=2;
    (dg.path||[]).forEach(([x,y],i)=>{ if(!inView(x,y)) return;
     ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4);
     if(i===0 && dg.state==="active"){ ctx.fillStyle="rgba(255,159,28,0.35)"; ctx.fillRect(sX(x)+2,sY(y)+2,scale-4,scale-4); } });
    ctx.globalAlpha=0.6;
    (dg.forts||[]).forEach(([x,y])=>{ if(!inView(x,y)) return; box(x,y,"#8957e5");
     if(scale>=16){ ctx.font=Math.min(scale-3,16)+"px system-ui"; ctx.textAlign="center"; ctx.textBaseline="middle";
      ctx.fillText("🏯", sX(x)+scale/2, sY(y)+scale/2); } });
    ctx.globalAlpha=1;
    ctx.strokeStyle="#da3633"; ctx.lineWidth=2;
    (dg.hard||[]).forEach(([x,y])=>{ if(!inView(x,y)) return; ctx.beginPath();
     ctx.moveTo(sX(x)+3,sY(y)+3); ctx.lineTo(sX(x)+scale-3,sY(y)+scale-3);
     ctx.moveTo(sX(x)+scale-3,sY(y)+3); ctx.lineTo(sX(x)+3,sY(y)+scale-3); ctx.stroke(); });
    const t=dg.target_xy;
    if(t && inView(t[0],t[1])){ ctx.strokeStyle="#ff9f1c"; ctx.lineWidth=3;
     ctx.strokeRect(sX(t[0])+1,sY(t[1])+1,scale-2,scale-2);
     if(scale>=14){ ctx.font=Math.min(scale-3,16)+"px system-ui"; ctx.textAlign="center"; ctx.textBaseline="middle";
      ctx.fillText("🎯", sX(t[0])+scale/2, sY(t[1])+scale/2); } }
   }
   // Forts under construction (faded purple + 🏗) and waiting to be built (dashed purple).
   ctx.globalAlpha=0.55;
   data.building.forEach(b=>{ if(!inView(b.x,b.y)) return; box(b.x,b.y,"#8957e5");
    if(scale>=16){ ctx.font=Math.min(scale-3,16)+"px system-ui"; ctx.textAlign="center"; ctx.textBaseline="middle";
     ctx.fillText("🏗", sX(b.x)+scale/2, sY(b.y)+scale/2); } });
   ctx.globalAlpha=1;
   ctx.strokeStyle="#8957e5"; ctx.lineWidth=2; ctx.setLineDash([3,2]);
   data.pending.forEach(p=>{ if(inView(p.x,p.y)) ctx.strokeRect(sX(p.x)+2,sY(p.y)+2,scale-4,scale-4); });
   ctx.setLineDash([]);
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
   // per-cell troop view from /api/armies (has index/name/state/pawns) — like the
   // in-game map's army markers. Grouped by cell index: count of armies + pawns +
   // the most-active state (idle < march < fight) for the cell's colour.
   const arms=(await getJSON("/api/armies"))||[];
   const dg=await getJSON("/api/dig"); if(dg) dig.value=dg;
   const armyCells={};
   arms.forEach(a=>{ const i=(a&&a.index)|0; if(!i) return;
    const c=armyCells[i]||(armyCells[i]={x:i%mw, y:Math.floor(i/mw), armies:[], pawns:0, maxState:0});
    const n=((a.pawns)||[]).length;
    c.armies.push({name:a.name||"?", state:(a.state)|0, label:a.state_label||"", pawns:n});
    c.pawns+=n; c.maxState=Math.max(c.maxState,(a.state)|0); });
   data={ main:t.main_city||0, mw, owned:f.owned_cells||[], accepted:f.accepted||[],
    forts:f.forts||[],   // built Cứ Điểm from the chunk city decode (authoritative)
    garr:(t.garrisons||[]).map(i=>[i%mw, Math.floor(i/mw)]),
    enemy:f.enemy_cells||[], enemyCities:f.enemy_cities||[], frontier:f.frontier||[],
    ally:f.ally_cells||[], allyCities:f.ally_cities||[],
    zone:f.fort_zone||[], fortCount:f.fort_count||0, fortCap:f.fort_cap||0, armyCells,
    building:f.building||[], pending:f.pending||[] };
   zoneSet=new Set(data.zone.map(([x,y])=>x+","+y));
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
   const ac=data.armyCells[idx(c.x,c.y)];
   let txt=`(${c.x}, ${c.y})`+(st?` · ${st.label}`:" · trống");
   if(ac) txt+=` · ${ac.armies.length} đội / ${ac.pawns} lính`;
   tip.value={ left:(ev.clientX-r.left)+12, top:(ev.clientY-r.top)+12, text:txt };
   render();
  }
  function onUp(ev){ dragging=false;
   if(moved<4){ const [px,py]=toCanvas(ev);
    if(px>=ML&&py>=MT){ const c=cellAt(px,py), st=stateMap.get(idx(c.x,c.y));
     const r=canvas.value.getBoundingClientRect();
     const ac=data.armyCells[idx(c.x,c.y)];
     const inZone=zoneSet.has(c.x+","+c.y);
     sel.value={ x:c.x, y:c.y, index: st?st.index:idx(c.x,c.y), state: st?st.label:"trống",
       armies: ac?ac.armies:null, inZone,
       diggable: !st || st.label==="biên giới trống",
       capReached: data.fortCap>0 && data.fortCount>=data.fortCap,
       left:Math.min(ev.clientX-r.left, r.width-170), top:(ev.clientY-r.top) }; } } }
  function onLeave(){ hover=null; tip.value=null; render(); }
  function onWheel(ev){ ev.preventDefault(); const [px,py]=toCanvas(ev); zoomAt(px,py, ev.deltaY<0?1.15:1/1.15); }
  function zoomBtn(f){ const cv=canvas.value; zoomAt(cv.width/2, cv.height/2, f); }
  function recenterBtn(){ recenter(canvas.value); render(); }
  function fitBtn(){ fitView(canvas.value); render(); }
  const built=ref("");
  async function buildFort(){ if(!sel.value) return;
   const r=await postJSON("/api/forts/build",{index:sel.value.index});
   built.value=(r&&r.ok)?`Đã gửi lệnh xây Cứ Điểm @(${sel.value.x},${sel.value.y})`:((r&&r.error)||"Lỗi");
   sel.value=null; setTimeout(()=>{built.value="";}, 4000); load(); }

  const digMsg=ref("");
  async function digCmd(op, body){
   const r=await postJSON("/api/dig/"+op, body||{});
   if(r && r.ok){ dig.value=r; digMsg.value=""; } else digMsg.value=(r&&r.error)||"Lỗi";
   render(); }
  function digHere(){ if(!sel.value) return;
   const b=Math.max(0,Math.min(6,parseInt(digBuffer.value)||0));
   try{ localStorage.setItem("nta.digBuffer", String(b)); }catch(e){}
   digCmd("request",{index:sel.value.index, buffer:b}); sel.value=null; }
  const digConfirm=()=>digCmd("confirm");
  const digCancel=()=>digCmd("cancel");
  const digReplan=()=>digCmd("replan");

  onMounted(()=>{ const cv=canvas.value; if(cv) cv.addEventListener("wheel", onWheel, {passive:false}); });
  onUnmounted(()=>{ const cv=canvas.value; if(cv) cv.removeEventListener("wheel", onWheel); });

  return { canvas, tip, sel, built, onDown, onMove, onUp, onLeave, zoomBtn, recenterBtn, fitBtn, buildFort,
           dig, digBuffer, digMsg, digHere, digConfirm, digCancel, digReplan, fmtDur, DIG_STATE, DIG_REASON };
 },
 template:`<div class="card full"><h2>Lãnh thổ</h2>
  <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
   <button @click="zoomBtn(1.25)">＋</button><button @click="zoomBtn(0.8)">－</button>
   <button @click="fitBtn">Vừa khung</button><button @click="recenterBtn">Về thành chính</button>
   <span class="muted" style="font-size:12px">Kéo để di chuyển · cuộn để phóng to · bấm ô để xem toạ độ / ⛏ dig tới đó</span></div>
  <div v-if="dig.state && dig.state!=='idle'" class="digcard" style="border:1px solid #ff9f1c;border-radius:6px;
    padding:6px 10px;margin-bottom:6px;font-size:13px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">
   <b>⛏ Dig tới ({{ (dig.target_xy||[])[0] }}, {{ (dig.target_xy||[])[1] }})</b>
   <span>{{ DIG_STATE[dig.state] || dig.state }}</span>
   <span v-if="dig.cells!=null && ['preview','active','waiting'].includes(dig.state)">
    {{ dig.cells }} ô · ước tính {{ fmtDur(dig.total_s) }}
    <span v-if="(dig.forts||[]).length"> · {{ dig.forts.length }} Cứ Điểm dự kiến</span>
    <span v-if="dig.stamina"> · ~{{ dig.stamina }} thể lực</span></span>
   <span v-if="dig.retargets && dig.retargets.length" style="color:#e3b341">
    đích cũ bị chiếm → đổi sang ô gần nhất</span>
   <span v-if="dig.reason && dig.reason!=='ok' && DIG_REASON[dig.reason]" style="color:#e3b341">{{ DIG_REASON[dig.reason] }}</span>
   <span v-if="dig.reason==='blocked_by_hard' && dig.need_loss!=null" style="color:#e3b341">
    · nếu cho phép tổn thất ≥ {{ Math.ceil(dig.need_loss) }}% (hiện {{ dig.max_loss||0 }}%) thì dig được ngay</span>
   <span v-if="dig.rough" class="muted">(ước lượng thô — mô phỏng không sẵn sàng)</span>
   <span v-if="dig.pending && !dig.cancel_pending" class="muted">⏳ chờ agent xử lý (agent phải đang chạy)</span>
   <span class="muted" v-if="['preview','active'].includes(dig.state)">chưa tính thời gian chờ thể lực/hồi máu</span>
   <button v-if="dig.state==='preview' && ['ok','blocked_by_hard'].includes(dig.reason) && !dig.pending"
     @click="digConfirm">✔ Xác nhận dig</button>
   <button v-if="['preview','active','waiting','failed'].includes(dig.state)" :disabled="dig.pending"
     title="Tính lại từ đầu với dữ liệu bản đồ + mô phỏng mới" @click="digReplan">🔄 Tìm đường khác</button>
   <button v-if="['preview','previewing','active','waiting'].includes(dig.state)" @click="digCancel">✖ Huỷ mục tiêu</button>
   <span v-if="digMsg" style="color:#da3633">{{ digMsg }}</span>
  </div>
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
    <div v-if="sel.armies" style="font-size:12px;margin:2px 0">
     <div v-for="(a,i) in sel.armies" :key="i">🛡️ {{ a.name }} · <b>{{ a.pawns }}</b> lính
      <span class="muted">({{ a.label }})</span></div></div>
    <template v-if="sel.inZone">
     <div v-if="sel.capReached" class="muted" style="font-size:12px;color:#e3b341">Đã đủ số Cứ Điểm</div>
     <button v-else @click="buildFort">🏯 Xây Cứ Điểm ở đây</button></template>
    <div v-if="sel.diggable" style="font-size:12px;margin:4px 0">
     <button @click="digHere">⛏ Dig tới đây</button>
     <label class="muted"> cách địch ≥ <input type="number" min="0" max="6" v-model="digBuffer"
       style="width:3em"> ô</label></div>
    <button @click="sel=null">Đóng</button></div>
   <div v-if="built" class="muted" style="position:absolute;left:8px;bottom:8px;background:#0d1117;
     border:1px solid var(--border-hi);border-radius:4px;padding:2px 8px;font-size:12px;color:#199e70;z-index:8">{{ built }}</div>
  </div>
  <div class="muted" style="margin-top:6px;font-size:12px;display:flex;gap:12px;flex-wrap:wrap">
   <span><b style="color:#3987e5">■</b> thành chính</span>
   <span><b style="color:#199e70">■</b> ô đã chiếm (liền lãnh địa)</span>
   <span><b style="color:#e3b341">▢</b> ô đã chiếm nhưng RỜI (không nối với thành)</span>
   <span><b style="color:#39d0d8">⬡</b> bao lãnh địa (hull nối biên vùng liền chứa thành)</span>
   <span>🏯 <b style="color:#8957e5">■</b> Cứ Điểm đã xây (viền vàng) · 🏗 đang xây · <b style="color:#8957e5">▢</b> chờ xây</span>
   <span><b style="color:#d95926">▨</b> vùng gợi ý xây Cứ Điểm — bấm 1 ô để agent xây</span>
   <span>quân (số=lính): <b style="color:#c3c2b7">▢</b>rảnh <b style="color:#58a6ff">▢</b>hành quân <b style="color:#da3633">▢</b>đang đánh</span>
   <span><b style="color:#da3633">■</b> ô địch</span>
   <span><b style="color:#2f81f7">■</b> ô đồng minh (cùng liên minh)</span>
   <span><b class="muted">▢</b> biên giới trống (xấp xỉ)</span>
   <span><b style="color:#ff9f1c">▢</b> đường dig 🎯 đích · <b style="color:#da3633">✕</b> ô chưa đánh nổi</span>
   <span><b style="color:#F5E900">◇</b> vùng bảo vệ/tăng tốc = bán kính 6 ô (Manhattan) quanh thành 2×2 — không cần xây Cứ Điểm bên trong</span>
  </div></div>`
};
