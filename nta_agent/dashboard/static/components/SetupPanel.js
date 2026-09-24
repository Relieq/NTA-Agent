import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
// First-run checklist (packaged app). Each step self-checks and, where it can,
// performs itself (save adb path, read distinct id / token, extract game data).
// Start stays locked until every step passes.
export default {
 setup(){
  const s=ref({steps:[],ready:false,packaged:false});
  const running=ref(null); const msg=ref("");
  async function load(){ s.value=(await getJSON("/api/setup"))||s.value; }
  async function run(name){
   running.value=name; msg.value="";
   const r=await postJSON("/api/setup/run",{step:name});
   if(r&&r.error) msg.value=r.error;
   await load(); running.value=null;
   return r&&r.ok;
  }
  async function runAll(){
   for(const st of s.value.steps){ if(!(await run(st.name))) break; }
  }
  async function override(name){
   if(!confirm("Bản game khác bản app hỗ trợ có thể làm agent gửi lệnh sai. Vẫn tiếp tục?")) return;
   await postJSON("/api/setup/override",{step:name}); await load();
  }
  onMounted(load);
  return { s, running, msg, run, runAll, override };
 },
 template:`<div class="card full"><h2>Thiết lập lần đầu</h2>
  <div style="background:#3a2a05;border:1px solid #e3b341;color:#f5d98a;padding:6px 10px;border-radius:6px;font-size:12px;margin-bottom:8px">
   ⚠ Dùng bot có thể vi phạm điều khoản game và dẫn tới <b>khoá tài khoản</b> — bạn tự chịu rủi ro.
   Mỗi tài khoản chỉ có <b>một phiên</b>: khi agent chạy, game trong giả lập sẽ bị đăng xuất.</div>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Mở LDPlayer (đã bật root + ADB) và đăng nhập game trước. Chạy từng bước theo thứ tự;
   hướng dẫn chi tiết ở README đi kèm.</div>
  <table style="width:100%;font-size:13px;border-collapse:collapse">
   <tr v-for="(st,i) in s.steps" :key="st.name" style="border-top:1px solid var(--border,#30363d)">
    <td style="padding:6px 6px 6px 0;width:24px">{{ st.ok ? "✅" : (st.ran ? "❌" : "⬜") }}</td>
    <td style="padding:6px 8px 6px 0"><b>{{ i+1 }}. {{ st.title }}</b>
     <div class="muted" style="font-size:12px">{{ st.detail }}</div>
     <div v-if="st.hint && st.ran" style="font-size:12px;color:#f5d98a">➜ {{ st.hint }}
      <span class="muted">(README: {{ st.doc.split('#')[1] }})</span></div></td>
    <td style="text-align:right;white-space:nowrap">
     <button :disabled="!!running" @click="run(st.name)">{{ running===st.name ? "⏳" : (st.ok ? "Chạy lại" : "Chạy") }}</button>
     <button v-if="st.overridable && st.ran" :disabled="!!running" @click="override(st.name)">Bỏ qua</button></td>
   </tr></table>
  <div style="display:flex;gap:10px;align-items:center;margin-top:8px">
   <button :disabled="!!running" @click="runAll">▶ Chạy tất cả</button>
   <b v-if="s.ready" style="color:#199e70">Sẵn sàng — bấm ▶ Start ở góc trên.</b>
   <span v-else-if="s.packaged" class="muted">Start bị khoá tới khi mọi bước ✅.</span>
   <span v-if="msg" style="color:#da3633;font-size:12px">{{ msg }}</span></div>
 </div>`
};
