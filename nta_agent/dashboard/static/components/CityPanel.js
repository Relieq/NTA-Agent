import { getJSON, usePolling } from "../api.js";
const { ref, computed, onMounted } = window.Vue;

function fmt(ms){ if(!ms||ms<0) return ""; const s=Math.round(ms/1000); const m=Math.floor(s/60); return m+"m"+String(s%60).padStart(2,"0")+"s"; }

export default {
 setup(){
  const s=ref(null), names=ref({});
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:null; },2000);
  onMounted(async ()=>{ const p=await getJSON("/api/profile"); if(p&&p.names) names.value=p.names; });
  const nm=(id)=> names.value[String(id)] || ("#"+id);
  const builds=computed(()=> (s.value&&s.value.builds)||[]);
  const queue=computed(()=> (s.value&&s.value.build_queue)||[]);
  return { s, builds, queue, nm, fmt };
 },
 template:`<div class="card"><h2>Thành chính &amp; công trình</h2>
  <div class="muted">@{{ (s&&s.main_city_index)||"?" }} · hàng đợi {{ queue.length }}/{{ (s&&s.build_queue_slots)||0 }}</div>

  <h3 style="margin:10px 0 4px">🔨 Đang xây / nâng cấp</h3>
  <ul><li v-for="(b,i) in queue" :key="i">{{ nm(b.id) }} → <b>Lv{{ b.lv }}</b>
       <span class="muted" v-if="b.surplusTime"> · còn {{ fmt(b.surplusTime) }}</span></li>
   <li v-if="!queue.length" class="muted">(không có gì trong hàng đợi)</li></ul>

  <h3 style="margin:10px 0 4px">Công trình đã có</h3>
  <ul><li v-for="b in builds" :key="b.uid">{{ nm(b.id) }} <b>Lv{{ b.lv }}</b></li>
   <li v-if="!builds.length" class="muted">—</li></ul></div>`
};
