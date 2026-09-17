import { getJSON, usePolling } from "../api.js";
const { ref, computed } = window.Vue;
export default {
 setup(){
  const s=ref(null);
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:null; },2000);
  const builds=computed(()=> (s.value&&s.value.builds)||[]);
  const q=computed(()=> s.value&&s.value.build_queue? s.value.build_queue.length : 0);
  return { s, builds, q };
 },
 template:`<div class="card"><h2>Thành chính &amp; công trình</h2>
  <div class="muted">@{{ (s&&s.main_city_index)||"?" }} · hàng đợi {{ q }}/{{ (s&&s.build_queue_slots)||0 }}</div>
  <ul><li v-for="b in builds" :key="b.uid">{{ b.name||("#"+b.id) }} <b>Lv{{ b.lv }}</b></li>
   <li v-if="!builds.length" class="muted">—</li></ul></div>`
};
