import { getJSON, usePolling, hms } from "../api.js";
const { ref } = window.Vue;
function fmt(d){ return d==null? "" : (typeof d==="object" ? (d.rationale||JSON.stringify(d)) : String(d)); }
function line(e){
 return e.kind==="tick"
  ? ("tick "+e.i+" · "+((e.fired||[]).join(", ")||"—"))
  : (e.kind+(e.detail?(" · "+fmt(e.detail)):""));
}
export default {
 setup(){ const evs=ref([]);
  usePolling(async ()=>{ evs.value=((await getJSON("/api/events?n=50"))||[]).slice().reverse(); },2000);
  return { evs, hms, line }; },
 template:`<div class="card full"><h2>Sự kiện gần đây</h2>
  <ul class="feed"><li v-for="(e,i) in evs" :key="i"><span class="muted">{{ hms(e.ts) }}</span> {{ line(e) }}</li>
   <li v-if="!evs.length" class="muted">—</li></ul></div>`
};
