import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
// User settings. Secrets are write-only: the server returns only a mask
// (sk-…abcd) and the field stays blank unless the user types a new value.
const DEFAULT_MODEL="gpt-4o-mini";   // llm.default_chat default
const FIELDS=[
 {key:"openai_api_key", label:"OpenAI API key", secret:true,
  help:"Tuỳ chọn — bật \"bộ não\" (chiến lược + chat). Tính phí theo tài khoản OpenAI của bạn."},
 {key:"openai_model", label:"Model", kind:"model",
  help:"Danh sách lấy từ tài khoản OpenAI của bạn (cần key). Mặc định gpt-4o-mini."},
 {key:"brain_max_calls", label:"Giới hạn lượt gọi bộ não / phiên", placeholder:"50"},
 {key:"keep_awake", label:"Giữ máy không ngủ khi agent chạy", placeholder:"1 (bật) / 0 (tắt)",
  help:"Mặc định bật (Windows): chặn máy tự ngủ (kể cả Modern Standby) khi agent đang chạy; màn hình vẫn tự tắt được. Không chặn được việc bạn gập nắp / bấm nút nguồn. Có hiệu lực ở lần khởi động agent kế tiếp."},
 {key:"auto_emulator", label:"Tự bật giả lập khi cần token", placeholder:"1 (bật) / 0 (tắt)",
  help:"Mặc định bật: khi chuỗi token đứt, agent tự mở LDPlayer, lấy token rồi tắt lại (chỉ tắt nếu chính nó mở). Giả lập bạn đang tự dùng thì không bị đụng tới."},
 {key:"xxtea_key", label:"XXTEA key (tuỳ chọn)", secret:true,
  help:"Để trống — app tự tìm khoá trong chính bản game của bạn. Chỉ nhập nếu tự dò thất bại."},
 {key:"update_token", label:"GitHub token (cập nhật)", secret:true,
  help:"Để trống. Chỉ cần nếu kho phát hành chuyển sang riêng tư (token chỉ-đọc)."},
 {key:"adb_path", label:"Đường dẫn adb.exe", placeholder:"tự dò (LDPlayer)"},
 {key:"adb_serial", label:"Thiết bị ADB", placeholder:"emulator-5554"},
 {key:"game_version", label:"Phiên bản khai báo (thử nghiệm)", placeholder:"mặc định của app",
  help:"Số phiên bản agent gửi khi đăng nhập. Chỉ đổi để thử khi game vừa cập nhật: máy chủ chỉ nhận một khoảng phiên bản (quá thấp = 500060, quá cao = 500122). Giao thức và dữ liệu của agent vẫn lấy từ bản game đã cài, nên khai lệch có thể đăng nhập được nhưng lệnh sau đó sai. Để trống = dùng số mặc định."},
];
export default {
 setup(){
  const cur=ref({}); const draft=ref({}); const msg=ref(""); const ok=ref(true);
  const app=ref({}); const upd=ref(null);
  const models=ref([]); const modelsErr=ref(""); const custom=ref(false);
  const gu=ref(null);   // game data update (no emulator): cached check + apply progress
  let guTimer=null;
  async function loadGu(){ gu.value=await getJSON("/api/gameupdate");
   const run=gu.value&&gu.value.apply&&gu.value.apply.state==="running";
   if(run && !guTimer){ guTimer=setInterval(loadGu, 3000); }
   if(!run && guTimer){ clearInterval(guTimer); guTimer=null; } }
  async function checkGu(){ gu.value=await getJSON("/api/gameupdate?refresh=1"); }
  async function applyGu(){
   if(!confirm("Tải bản APK mới nhất từ trang tải game (~120 MB) và trích lại dữ liệu? Dữ liệu cũ được sao lưu. Không cần bật giả lập.")) return;
   const r=await postJSON("/api/gameupdate/apply",{});
   flash((r&&r.ok)?"Đang cập nhật dữ liệu game…":((r&&r.error)||"Lỗi"), !!(r&&r.ok));
   loadGu(); }
  async function loadModels(){
   const r=await getJSON("/api/settings/models");
   models.value=(r&&r.models)||[]; modelsErr.value=(r&&!r.ok&&r.error)||"";
  }
  // current value first if the account list lacks it (custom / older model)
  const modelOptions=()=>{
   const c=cur.value.openai_model; const cv=(c&&c.set&&c.value)||DEFAULT_MODEL;
   return models.value.includes(cv) ? models.value : [cv, ...models.value];
  };
  function pickModel(v){
   if(v==="__custom__"){ custom.value=true; draft.value.openai_model=""; }
   else { custom.value=false; draft.value.openai_model=v; }
  }
  async function load(){ cur.value=(await getJSON("/api/settings"))||{}; app.value=(await getJSON("/api/app"))||{};
   upd.value=await getJSON("/api/update/check"); loadModels(); loadGu(); }
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
   if(r&&r.ok){ draft.value={}; custom.value=false; cur.value=r.settings; flash("Đã lưu",true);
                if(body.openai_api_key) loadModels(); } else flash((r&&r.error)||"Lỗi",false);
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
  return { FIELDS, cur, draft, msg, ok, app, upd, save, clear, testKey, checkNow, rollback, gu, checkGu, applyGu,
           models, modelsErr, custom, loadModels, modelOptions, pickModel, DEFAULT_MODEL };
 },
 template:`<div class="card full"><h2>Cài đặt</h2>
  <div class="muted" style="font-size:12px;margin-bottom:6px">
   Key được mã hoá bằng tài khoản Windows của bạn (không mang sang máy khác được) và không bao giờ hiện lại đầy đủ.
   Phiên bản {{ app.version }} · dữ liệu: {{ app.data_dir }}</div>
  <table style="width:100%;font-size:13px;border-collapse:collapse">
   <tr v-for="f in FIELDS" :key="f.key" style="border-top:1px solid var(--border,#30363d)">
    <td style="padding:6px 8px 6px 0;width:34%"><b>{{ f.label }}</b>
     <div v-if="f.help" class="muted" style="font-size:11px">{{ f.help }}</div></td>
    <td v-if="f.kind==='model'" style="padding:6px 0">
     <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <select style="max-width:260px" :value="custom ? '__custom__' : (draft.openai_model || (cur.openai_model&&cur.openai_model.value) || DEFAULT_MODEL)"
       @change="pickModel($event.target.value)">
       <option v-for="m in modelOptions()" :key="m" :value="m">{{ m }}</option>
       <option value="__custom__">Khác… (tự nhập)</option>
      </select>
      <button title="Tải lại danh sách" @click="loadModels">↻</button>
      <input v-if="custom" type="text" autocomplete="off" style="width:180px" placeholder="tên model" v-model="draft.openai_model">
     </div>
     <div v-if="modelsErr" class="muted" style="font-size:11px">{{ modelsErr }}</div></td>
    <td v-else style="padding:6px 0">
     <input :type="f.secret?'password':'text'" autocomplete="off" style="width:100%;max-width:340px"
      :placeholder="(cur[f.key]&&cur[f.key].set) ? (f.secret ? 'đã lưu: '+cur[f.key].value : cur[f.key].value) : (f.placeholder||'chưa đặt')"
      v-model="draft[f.key]">
     <div v-if="cur[f.key]&&cur[f.key].source==='env'" class="muted" style="font-size:11px;color:#d29922">
      đang lấy từ biến môi trường của Windows — nhập giá trị ở đây để thay</div>
     <div v-else-if="cur[f.key]&&cur[f.key].env_also" class="muted" style="font-size:11px">
      (biến môi trường cũng có giá trị, nhưng app dùng giá trị đã lưu ở đây)</div></td>
    <td style="text-align:right;white-space:nowrap">
     <button v-if="cur[f.key]&&cur[f.key].set" @click="clear(f.key)">Xoá</button></td>
   </tr></table>
  <div style="border-top:1px solid var(--border,#30363d);margin-top:10px;padding-top:8px;font-size:13px">
   <b>Dữ liệu game</b> <span class="muted" style="font-size:12px">— cập nhật từ trang tải game, không cần bật giả lập</span>
   <div v-if="gu && gu.status" style="margin-top:4px">
    Đang dùng script <b>{{ gu.status.installed_scripts }}</b> · trang tải: APK <b>{{ (gu.status.published||{}).apk_version }}</b>
    <span v-if="gu.status.update_available" style="color:#d29922"> · có bản mới: {{ gu.status.reason }}</span>
    <span v-else style="color:#199e70"> · đã mới nhất</span></div>
   <div v-if="gu && gu.error" style="color:#da3633;font-size:12px">{{ gu.error }}</div>
   <div v-if="gu && gu.apply" class="muted" style="font-size:12px">Lần cập nhật gần nhất: {{ gu.apply.state }} — {{ gu.apply.detail }}</div>
   <div style="display:flex;gap:10px;align-items:center;margin-top:4px;flex-wrap:wrap">
    <button @click="checkGu">Kiểm tra bản game mới</button>
    <button :disabled="gu && (gu.agent_running || (gu.apply && gu.apply.state==='running'))" @click="applyGu"
     :title="gu && gu.agent_running ? 'Dừng agent trước' : 'Tải APK, trích khoá + dữ liệu, sao lưu bản cũ'">Cập nhật dữ liệu game</button>
    <span v-if="gu && gu.agent_running" class="muted" style="font-size:12px">dừng agent trước khi cập nhật</span></div></div>
  <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap">
   <button @click="save">Lưu</button>
   <button @click="testKey">Kiểm tra OpenAI key</button>
   <template v-if="app.packaged">
    <button @click="checkNow">Kiểm tra cập nhật</button>
    <button v-if="upd && upd.has_backup" @click="rollback">↩ Quay về bản trước</button></template>
   <span v-if="msg" :style="{color: ok ? '#199e70' : '#da3633', fontSize:'12px'}">{{ msg }}</span></div>
 </div>`
};
