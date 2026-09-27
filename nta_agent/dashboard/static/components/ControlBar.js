import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const COLOR={RUNNING:"var(--ok)",PAUSED:"var(--warn)",STOPPED:"var(--muted)",CRASHED:"var(--danger)"};
export default {
 setup(){
  const st=ref({engine:"STOPPED",pid:null,uptime:0}); const busy=ref(false); const err=ref(""); const showLog=ref(false);
  usePolling(async ()=>{ const s=await getJSON("/api/agent/status"); if(s) st.value=s; },1000);
  async function act(name){ busy.value=true;
   const s=await postJSON("/api/agent/"+name,{}); if(s) st.value=s; busy.value=false;
   // status polling overwrites st every second, so keep the refusal visible on its own
   if(s&&s.error){ err.value=s.error; setTimeout(()=>{err.value="";},8000); } }
  const alive=()=> st.value.engine==="RUNNING"||st.value.engine==="PAUSED";
  const bye=ref("");
  async function app(name){   // quit / restart the whole app (#81)
   const q= name==="quit" ? "Thoát NTA-Agent? Agent sẽ dừng và dashboard tắt hẳn."
    : "Khởi động lại NTA-Agent? Agent sẽ dừng; app mở lại và đọc lại biến môi trường.";
   if(!window.confirm(q)) return;
   await postJSON("/api/app/"+name,{});
   bye.value= name==="quit" ? "Đã thoát — có thể đóng tab này." : "Đang khởi động lại…";
   if(name==="restart") setTimeout(function wait(){ fetch("/api/app").then(r=>r.ok?location.reload():0)
    .catch(()=>setTimeout(wait,1000)); },2500); }
  const color=()=> COLOR[st.value.engine]||"var(--muted)";
  return { st, busy, err, showLog, act, alive, color, app, bye };
 },
 template:`<div style="display:flex;align-items:center;gap:8px;position:relative">
  <span class="dot" :style="{background:color()}"></span>
  <b :style="{color:color()}">{{ st.engine }}</b>
  <button :disabled="busy||alive()" @click="act('start')">▶ Start</button>
  <button v-if="st.engine!=='PAUSED'" :disabled="busy||!alive()" @click="act('pause')">⏸ Pause</button>
  <button v-else :disabled="busy" @click="act('resume')">▶ Resume</button>
  <button :disabled="busy||!alive()" @click="act('stop')">⏹ Stop</button>
  <button :disabled="busy" @click="app('restart')" title="Khởi động lại cả app (đọc lại biến môi trường)">↻</button>
  <button :disabled="busy" @click="app('quit')" title="Thoát hẳn NTA-Agent (dừng agent + tắt dashboard)">⏻</button>
  <span v-if="bye" style="color:#d29922;font-size:12px">{{ bye }}</span>
  <span v-if="err" style="color:#da3633;font-size:12px">{{ err }}</span>
  <button v-if="st.engine==='CRASHED' && st.log_tail && st.log_tail.length" @click="showLog=!showLog"
   title="Các dòng cuối trong build/run/agent.log">📄 Xem lỗi</button>
  <pre v-if="showLog && st.engine==='CRASHED'" style="position:absolute;top:100%;right:0;z-index:20;margin-top:6px;
   max-width:720px;max-height:320px;overflow:auto;background:#0d1117;border:1px solid #da3633;color:#ffb3ad;
   padding:8px;border-radius:6px;font-size:11px;white-space:pre-wrap">{{ (st.log_tail||[]).join("\\n") }}</pre>
 </div>`
};
