import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const s=ref({}), p=ref({});
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:{}; p.value=(v&&v.player)||{}; },2000);
  return { s, p };
 },
 template:`<div class="card"><h2>Quân &amp; nhiệm vụ</h2>
  <div class="kv">Đội hành quân <b>{{ s.marches??0 }}</b> · Ô đã biết <b>{{ s.areas??0 }}</b></div>
  <div class="kv" style="margin-top:8px">Guide <b>{{ p.guide_tasks??0 }}</b> · Other <b>{{ p.other_tasks??0 }}</b> · Today <b>{{ p.today_tasks??0 }}</b></div></div>`
};
