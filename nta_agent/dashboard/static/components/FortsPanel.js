import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const f=ref({owned_count:0,recommendations:[],accepted:[],rejected:[]});
  async function load(){ const v=await getJSON("/api/forts");
   if(v) f.value={owned_count:v.owned_count||0,recommendations:v.recommendations||[],
                  accepted:v.accepted||[],rejected:v.rejected||[]}; }
  usePolling(load, 4000);
  async function decide(index, decision){ await postJSON("/api/forts/decide",{index,decision}); load(); }
  const toIdx=([x,y])=> y*600 + x;  // map_width 600 (matches server)
  return { f, decide, toIdx };
 },
 template:`<div class="card full"><h2>Cứ Điểm — gợi ý</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b></div>
  <div style="margin-top:6px">
   <div v-for="(r,i) in f.recommendations" :key="'r'+i" style="display:flex;align-items:center;gap:8px;padding:2px 0">
    <span style="flex:1">{{ i+1 }}. Cứ Điểm @{{ r.index }} ({{ r.x }},{{ r.y }}) — {{ r.reason||"" }}</span>
    <button @click="decide(r.index,'accept')">✓ Chấp thuận</button>
    <button @click="decide(r.index,'reject')">✕ Từ chối</button></div>
   <div v-if="!f.recommendations.length" class="muted">Chưa có gợi ý</div>
  </div>
  <div v-if="f.accepted.length" style="margin-top:8px">
   <div class="muted" style="font-size:12px">Đã chấp thuận (dự kiến xây):</div>
   <div v-for="(a,i) in f.accepted" :key="'a'+i">🟧 ({{ a[0] }},{{ a[1] }})
    <button @click="decide(toIdx(a),'clear')">×</button></div></div>
  <div v-if="f.rejected.length" style="margin-top:8px">
   <div class="muted" style="font-size:12px">Đã từ chối:</div>
   <div v-for="(a,i) in f.rejected" :key="'j'+i" class="muted">✕ ({{ a[0] }},{{ a[1] }})
    <button @click="decide(toIdx(a),'clear')">×</button></div></div>
 </div>`
};
