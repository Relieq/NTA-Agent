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
