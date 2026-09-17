import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ds=ref([]);
  usePolling(async ()=>{ ds.value=(await getJSON("/api/decisions"))||[]; },2000);
  const sending=ref({});
  const skey=(d,o)=> d.track+":"+d.lv+":"+(o?o.ceri_id:"reroll");
  async function act(d, o){
   const key=skey(d,o);
   sending.value={...sending.value,[key]:true};
   const cmd=o? {action:"select",track:d.track,lv:d.lv,ceri_id:o.ceri_id}
             : {action:"reroll",track:d.track,lv:d.lv};
   await postJSON("/api/command", cmd);
  }
  return { ds, act, sending, skey };
 },
 template:`<div class="card full"><h2>Quyết định đang chờ</h2>
  <span v-if="!ds.length" class="muted">—</span>
  <div v-for="d in ds" :key="d.track+d.lv" style="margin:6px 0">
   <span class="muted">{{ d.track }} · Lv{{ d.lv }}</span><br>
   <template v-for="o in (d.options||[])" :key="o.ceri_id">
    <button :disabled="sending[skey(d,o)]" @click="act(d,o)">{{ sending[skey(d,o)]?"đã gửi…":o.name }}</button>
    <span v-if="o.desc" class="muted">{{ o.desc }}</span><br></template>
   <button :disabled="sending[skey(d,null)]" @click="act(d,null)">{{ sending[skey(d,null)]?"đã gửi…":("Làm mới"+(d.reset_count?(" ("+d.reset_count+")"):" (free)")) }}</button>
  </div></div>`
};
