import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;

// Phase (nâng lính): user designates the fixed farm army + a dedicated leveling
// army + target level; the agent runs the exp-book level+swap cycle.
export default {
 setup(){
  const armies = ref([]);
  const cfg = ref({ enabled:false, target_lv:0, farm_uid:"", army_uid:"" });
  const saved = ref("");

  async function load(){
   const a = await getJSON("/api/armies"); armies.value = Array.isArray(a) ? a : [];
   const p = await getJSON("/api/profile");
   if (p && p.leveling) cfg.value = Object.assign(cfg.value, p.leveling);
  }
  onMounted(load);

  async function save(){
   saved.value = "";
   const body = { leveling: {
     enabled: !!cfg.value.enabled,
     target_lv: Number(cfg.value.target_lv) || 0,
     farm_uid: cfg.value.farm_uid || "",
     army_uid: cfg.value.army_uid || "",
   }};
   const r = await postJSON("/api/profile", body);
   saved.value = (r && r.ok) ? "Đã lưu ✓" : "Lưu lỗi";
  }
  return { armies, cfg, saved, save };
 },
 template:`<div class="card"><h2>Nâng cấp lính (sách exp)</h2>
  <div class="kv" style="color:#8b949e;margin-bottom:8px">
   Agent nâng lính trong <b>đội nâng</b> tới cấp mục tiêu, rồi tráo vào <b>đội farm</b> khi về thành.</div>

  <label class="kv" style="display:block;margin:6px 0">
   <input type="checkbox" v-model="cfg.enabled"/> Bật tự động nâng cấp</label>

  <label class="kv" style="display:block;margin:6px 0">Cấp mục tiêu
   <input type="number" min="0" v-model="cfg.target_lv" style="width:70px;margin-left:6px"/></label>

  <label class="kv" style="display:block;margin:6px 0">Đội farm cố định
   <select v-model="cfg.farm_uid" style="margin-left:6px">
    <option value="">— chọn —</option>
    <option v-for="a in armies" :key="a.uid" :value="a.uid">{{ a.name||a.uid }}</option>
   </select></label>

  <label class="kv" style="display:block;margin:6px 0">Đội nâng cấp
   <select v-model="cfg.army_uid" style="margin-left:6px">
    <option value="">— chọn —</option>
    <option v-for="a in armies" :key="a.uid" :value="a.uid">{{ a.name||a.uid }}</option>
   </select></label>

  <button @click="save" style="margin-top:8px">Lưu cấu hình</button>
  <span class="kv" style="margin-left:10px;color:#199e70">{{ saved }}</span>
 </div>`
};
