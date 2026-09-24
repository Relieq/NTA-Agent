import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const COLOR={RUNNING:"var(--ok)",PAUSED:"var(--warn)",STOPPED:"var(--muted)",CRASHED:"var(--danger)"};
export default {
 setup(){
  const st=ref({engine:"STOPPED",pid:null,uptime:0}); const busy=ref(false); const err=ref("");
  usePolling(async ()=>{ const s=await getJSON("/api/agent/status"); if(s) st.value=s; },1000);
  async function act(name){ busy.value=true;
   const s=await postJSON("/api/agent/"+name,{}); if(s) st.value=s; busy.value=false;
   // status polling overwrites st every second, so keep the refusal visible on its own
   if(s&&s.error){ err.value=s.error; setTimeout(()=>{err.value="";},8000); } }
  const alive=()=> st.value.engine==="RUNNING"||st.value.engine==="PAUSED";
  const color=()=> COLOR[st.value.engine]||"var(--muted)";
  return { st, busy, err, act, alive, color };
 },
 template:`<div style="display:flex;align-items:center;gap:8px">
  <span class="dot" :style="{background:color()}"></span>
  <b :style="{color:color()}">{{ st.engine }}</b>
  <button :disabled="busy||alive()" @click="act('start')">▶ Start</button>
  <button v-if="st.engine!=='PAUSED'" :disabled="busy||!alive()" @click="act('pause')">⏸ Pause</button>
  <button v-else :disabled="busy" @click="act('resume')">▶ Resume</button>
  <button :disabled="busy||!alive()" @click="act('stop')">⏹ Stop</button>
  <span v-if="err" style="color:#da3633;font-size:12px">{{ err }}</span>
 </div>`
};
