export async function getJSON(u){ try{ const r=await fetch(u); return await r.json(); }catch(e){ return null; } }
export async function postJSON(u, body){
 try{ const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      return await r.json(); }catch(e){ return null; }
}
export function usePolling(fn, ms){
 const { onMounted, onUnmounted } = window.Vue;
 onMounted(()=>{ fn(); const id=setInterval(fn, ms); onUnmounted(()=>clearInterval(id)); });
}
export function ago(ts){ if(!ts) return ""; const s=Math.max(0,Math.round(Date.now()/1000-ts)); return s+"s trước"; }
export function hms(ts){ return new Date((ts||0)*1000).toLocaleTimeString(); }

// "✖ Ẩn" on a notice: remembered per viewer in localStorage (a convenience, never state the
// agent needs). An entry expires after a week so a condition that comes back later shows again.
const HIDE_KEY="nta.hidden", HIDE_TTL_MS=7*86400*1000;
function loadHidden(){
 try{ const o=JSON.parse(localStorage.getItem(HIDE_KEY)||"{}"), now=Date.now();
      for(const k of Object.keys(o)) if(!(now-o[k]<HIDE_TTL_MS)) delete o[k];
      return o; }catch(e){ return {}; }
}
export function useHidden(prefix){
 const { ref } = window.Vue;
 const hidden=ref(loadHidden());
 const id=(t)=>prefix+":"+t;
 const isHidden=(t)=>!!hidden.value[id(t)];
 const save=(o)=>{ hidden.value=o; try{ localStorage.setItem(HIDE_KEY, JSON.stringify(o)); }catch(e){} };
 function hide(t){ save({...loadHidden(), [id(t)]:Date.now()}); }
 function showAll(){ const o=loadHidden(); for(const k of Object.keys(o)) if(k.startsWith(prefix+":")) delete o[k]; save(o); }
 const hiddenCount=()=>Object.keys(hidden.value).filter(k=>k.startsWith(prefix+":")).length;
 return { isHidden, hide, showAll, hiddenCount };
}
