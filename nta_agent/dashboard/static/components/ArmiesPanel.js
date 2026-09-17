import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const armies=ref([]); const open=ref({});
  usePolling(async ()=>{ armies.value=(await getJSON("/api/armies"))||[]; },2000);
  function toggle(uid){ open.value={...open.value, [uid]: !open.value[uid]}; }
  return { armies, open, toggle };
 },
 template:`<div class="card full"><h2>Đội quân</h2>
  <span v-if="!armies.length" class="muted">—</span>
  <div v-for="a in armies" :key="a.uid" style="margin:4px 0">
   <div @click="toggle(a.uid)" style="cursor:pointer;display:flex;align-items:center;gap:6px">
    <span class="muted" style="width:12px">{{ open[a.uid] ? "▾" : "▸" }}</span>
    <b>{{ a.name||a.uid }}</b>
    <span class="muted">· {{ a.state_label }} · tốc hành quân {{ a.march_speed }} · {{ (a.pawns||[]).length }} lính</span></div>
   <ul v-show="open[a.uid]" style="margin-left:18px">
    <li v-for="(p,i) in (a.pawns||[])" :key="i">{{ i+1 }}. {{ p.name }} <b>Lv{{ p.lv }}</b> · tốc {{ p.attack_speed }} · {{ p.equip_name||"—" }}</li>
    <li v-if="!(a.pawns||[]).length" class="muted">trống</li></ul></div></div>`
};
