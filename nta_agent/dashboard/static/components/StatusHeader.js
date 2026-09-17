import { getJSON, usePolling, ago } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ok=ref(false), text=ref("…");
  usePolling(async ()=>{
   const s=await getJSON("/api/state");
   if(!s||!s.ok){ ok.value=false; text.value="Đang chờ agent…"; }
   else{ ok.value=true; text.value="đang chạy · "+ago(s.updated_at); }
  }, 2000);
  return { ok, text };
 },
 template:`<header><h1>NTA Agent</h1>
  <div><span class="dot" :class="ok?'on':'wait'"></span><span>{{ text }}</span></div></header>`
};
