import { getJSON, usePolling } from "../api.js";
const { ref, computed, onMounted, onUnmounted } = window.Vue;

function fmt(ms){ if(!ms||ms<0) return ""; const s=Math.round(ms/1000); const m=Math.floor(s/60); return m+"m"+String(s%60).padStart(2,"0")+"s"; }
// live remaining: prefer absolute endAt (ticks down), fall back to static surplusTime
function remain(b, now){ return (b&&b.endAt) ? (b.endAt - now) : (b&&b.surplusTime); }

export default {
 setup(){
  const s=ref(null), names=ref({}), now=ref(Date.now());
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:null; },2000);
  let timer=null;
  onMounted(async ()=>{ const p=await getJSON("/api/profile"); if(p&&p.names) names.value=p.names;
   timer=setInterval(()=>{ now.value=Date.now(); },1000); });
  onUnmounted(()=>{ if(timer) clearInterval(timer); });
  const nm=(id)=> names.value[String(id)] || ("#"+id);
  const builds=computed(()=> (s.value&&s.value.builds)||[]);
  const queue=computed(()=> (s.value&&s.value.build_queue)||[]);
  return { s, builds, queue, nm, fmt, remain, now };
 },
 template:`<div class="card"><h2>Thành chính &amp; công trình</h2>
  <div class="muted">@{{ (s&&s.main_city_index)||"?" }} · hàng đợi {{ queue.length }}/{{ (s&&s.build_queue_slots)||0 }}</div>

  <h3 style="margin:10px 0 4px">🔨 Đang xây / nâng cấp</h3>
  <ul><li v-for="(b,i) in queue" :key="i">{{ nm(b.id) }} → <b>Lv{{ b.lv }}</b>
       <span class="muted" v-if="remain(b,now)>0"> · còn {{ fmt(remain(b,now)) }}</span>
       <span class="muted" v-else> · sắp xong…</span></li>
   <li v-if="!queue.length" class="muted">(không có gì trong hàng đợi)</li></ul>

  <h3 style="margin:10px 0 4px">Công trình đã có</h3>
  <ul><li v-for="b in builds" :key="b.uid">{{ nm(b.id) }} <b>Lv{{ b.lv }}</b></li>
   <li v-if="!builds.length" class="muted">—</li></ul></div>`
};
