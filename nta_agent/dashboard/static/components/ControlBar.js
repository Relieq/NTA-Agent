import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const COLOR={RUNNING:"var(--ok)",PAUSED:"var(--warn)",STOPPED:"var(--muted)",CRASHED:"var(--danger)"};
export default {
 setup(){
  const st=ref({engine:"STOPPED",pid:null,uptime:0}); const busy=ref(false);
  usePolling(async ()=>{ const s=await getJSON("/api/agent/status"); if(s) st.value=s; },1000);
  async function act(name){ busy.value=true;
   const s=await postJSON("/api/agent/"+name,{}); if(s) st.value=s; busy.value=false; }
  const alive=()=> st.value.engine==="RUNNING"||st.value.engine==="PAUSED";
  const color=()=> COLOR[st.value.engine]||"var(--muted)";
  return { st, busy, act, alive, color };
 },
 template:`<div style="display:flex;align-items:center;gap:8px">
  <span class="dot" :style="{background:color()}"></span>
  <b :style="{color:color()}">{{ st.engine }}</b>
  <button :disabled="busy||alive()" @click="act('start')">▶ Start</button>
  <button v-if="st.engine!=='PAUSED'" :disabled="busy||!alive()" @click="act('pause')">⏸ Pause</button>
  <button v-else :disabled="busy" @click="act('resume')">▶ Resume</button>
  <button :disabled="busy||!alive()" @click="act('stop')">⏹ Stop</button>
 </div>`
};
