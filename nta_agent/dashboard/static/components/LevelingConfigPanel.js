import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;

// Nâng cấp lính: farm = nhóm đội active (profile.army.group); agent tự tạo 1 đội
// nâng (buffer) để nâng lính dưới cấp rồi tráo lại. User chỉ đặt bật/cấp/buffer.
export default {
 setup(){
  const cfg = ref({ enabled:false, target_lv:0, max_leveling:1 });
  const active = ref(""); const groupN = ref(0); const saved = ref("");

  async function load(){
   const p = await getJSON("/api/profile");
   if (p){
    if (p.leveling) cfg.value = Object.assign(cfg.value, p.leveling);
    active.value = p.active || "";
   }
  }
  onMounted(load);

  async function save(){
   saved.value = "";
   const r = await postJSON("/api/profile", { leveling: {
     enabled: !!cfg.value.enabled,
     target_lv: Number(cfg.value.target_lv) || 0,
     max_leveling: Number(cfg.value.max_leveling) || 1,
   }});
   saved.value = (r && r.ok) ? "Đã lưu ✓" : "Lưu lỗi";
  }
  return { cfg, active, saved, save };
 },
 template:`<div class="card"><h2>Nâng cấp lính (sách exp)</h2>
  <div class="kv" style="color:#8b949e;margin-bottom:8px">
   <b>Đội farm</b> = nhóm đội active (đặt ở phần đội hình, tối đa 5 đội). Agent <b>tự tạo đội nâng</b>
   để rút lính dưới cấp ra nâng bằng sách exp, rồi <b>tráo</b> lính đạt cấp vào nhóm farm khi về thành.</div>

  <div class="kv" style="margin-bottom:6px">Đội hình active: <b>{{ active || '(mặc định)' }}</b></div>

  <label class="kv" style="display:block;margin:6px 0">
   <input type="checkbox" v-model="cfg.enabled"/> Bật tự động nâng cấp</label>

  <label class="kv" style="display:block;margin:6px 0">Cấp mục tiêu
   <input type="number" min="0" v-model="cfg.target_lv" style="width:70px;margin-left:6px"/></label>

  <label class="kv" style="display:block;margin:6px 0">Số lính nâng đồng thời (buffer)
   <input type="number" min="1" v-model="cfg.max_leveling" style="width:70px;margin-left:6px"/></label>

  <button @click="save" style="margin-top:8px">Lưu cấu hình</button>
  <span class="kv" style="margin-left:10px;color:#199e70">{{ saved }}</span>
 </div>`
};
