import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
// User settings. Secrets are write-only: the server returns only a mask
// (sk-…abcd) and the field stays blank unless the user types a new value.
const FIELDS=[
 {key:"openai_api_key", label:"OpenAI API key", secret:true,
  help:"Tuỳ chọn — bật \"bộ não\" (chiến lược + chat). Tính phí theo tài khoản OpenAI của bạn."},
 {key:"openai_model", label:"Model", placeholder:"gpt-4o-mini"},
 {key:"brain_max_calls", label:"Giới hạn lượt gọi bộ não / phiên", placeholder:"50"},
 {key:"xxtea_key", label:"XXTEA key", secret:true,
  help:"Tuỳ chọn — bật mô phỏng trận (dự đoán thắng/thua). Sau khi nhập, chạy lại bước \"Dữ liệu game\"."},
 {key:"adb_path", label:"Đường dẫn adb.exe", placeholder:"tự dò (LDPlayer)"},
 {key:"adb_serial", label:"Thiết bị ADB", placeholder:"emulator-5554"},
];
export default {
 setup(){
  const cur=ref({}); const draft=ref({}); const msg=ref(""); const ok=ref(true);
  const app=ref({}); const upd=ref(null);
  async function load(){ cur.value=(await getJSON("/api/settings"))||{}; app.value=(await getJSON("/api/app"))||{};
   upd.value=await getJSON("/api/update/check"); }
  async function checkNow(){ upd.value=await getJSON("/api/update/check?force=1");
   flash(upd.value&&upd.value.update ? "Có bản mới "+upd.value.update.version : ((upd.value&&upd.value.error)||"Đang dùng bản mới nhất"), true); }
  async function rollback(){
   if(!confirm("Quay về phiên bản trước? Agent sẽ dừng và app khởi động lại.")) return;
   const r=await postJSON("/api/update/rollback",{});
   flash((r&&r.ok) ? "Đang quay về bản cũ… tải lại trang sau ~1 phút." : ((r&&r.error)||"Lỗi"), !!(r&&r.ok));
  }
  function flash(t,good){ msg.value=t; ok.value=good; setTimeout(()=>{msg.value="";},4000); }
  async function save(){
   const body={};
   for(const f of FIELDS){ const v=draft.value[f.key]; if(v!==undefined && v!=="") body[f.key]=v; }
   if(!Object.keys(body).length){ flash("Không có thay đổi",false); return; }
   const r=await postJSON("/api/settings",body);
   if(r&&r.ok){ draft.value={}; cur.value=r.settings; flash("Đã lưu",true); } else flash((r&&r.error)||"Lỗi",false);
  }
  async function clear(key){
   const r=await postJSON("/api/settings",{[key]:""});
   if(r&&r.ok){ cur.value=r.settings; flash("Đã xoá",true); }
  }
  async function testKey(){
   msg.value="Đang kiểm tra…"; ok.value=true;
   const r=await postJSON("/api/settings/test-key",{});
   flash(r&&r.ok ? "Key hợp lệ ✅" : ((r&&r.error)||"Lỗi"), !!(r&&r.ok));
  }
  onMounted(load);
  return { FIELDS, cur, draft, msg, ok, app, upd, save, clear, testKey, checkNow, rollback };
 },
 template:`<div class="card full"><h2>Cài đặt</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Key được mã hoá bằng tài khoản Windows của bạn (không mang sang máy khác được) và không bao giờ hiện lại đầy đủ.
   Phiên bản {{ app.version }} · dữ liệu: {{ app.data_dir }}</div>
  <table style="width:100%;font-size:13px;border-collapse:collapse">
   <tr v-for="f in FIELDS" :key="f.key" style="border-top:1px solid var(--border,#30363d)">
    <td style="padding:6px 8px 6px 0;width:34%"><b>{{ f.label }}</b>
     <div v-if="f.help" class="muted" style="font-size:11px">{{ f.help }}</div></td>
    <td style="padding:6px 0">
     <input :type="f.secret?'password':'text'" autocomplete="off" style="width:100%;max-width:340px"
      :placeholder="(cur[f.key]&&cur[f.key].set) ? (f.secret ? 'đã lưu: '+cur[f.key].value : cur[f.key].value) : (f.placeholder||'chưa đặt')"
      v-model="draft[f.key]"></td>
    <td style="text-align:right;white-space:nowrap">
     <button v-if="cur[f.key]&&cur[f.key].set" @click="clear(f.key)">Xoá</button></td>
   </tr></table>
  <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap">
   <button @click="save">Lưu</button>
   <button @click="testKey">Kiểm tra OpenAI key</button>
   <template v-if="app.packaged">
    <button @click="checkNow">Kiểm tra cập nhật</button>
    <button v-if="upd && upd.has_backup" @click="rollback">↩ Quay về bản trước</button></template>
   <span v-if="msg" :style="{color: ok ? '#199e70' : '#da3633', fontSize:'12px'}">{{ msg }}</span></div>
 </div>`
};
