import { getJSON, usePolling, ago } from "../api.js";
import ControlBar from "./ControlBar.js";
const { ref } = window.Vue;
export default {
 components:{ ControlBar },
 setup(){
  const snap=ref("…");
  usePolling(async ()=>{
   const s=await getJSON("/api/state");
   snap.value=(s&&s.ok)? ("snapshot "+ago(s.updated_at)) : "chưa có snapshot";
  }, 2000);
  return { snap };
 },
 template:`<header><div><h1>NTA Agent</h1><div class="muted" style="font-size:12px">{{ snap }}</div></div>
  <ControlBar/></header>`
};
