import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, onMounted } = window.Vue;

// Đội farm = profile.army.group: nhóm đội agent coi là "đội farm cố định". Nâng-lính
// rút lính dưới cấp TỪ nhóm này; occupy ưu tiên nhóm này. Không chọn -> nâng-lính đứng im.
export default {
 setup(){
  const armies = ref([]); const group = ref([]); const saved = ref("");

  async function load(){
   const a = await getJSON("/api/armies"); if (Array.isArray(a)) armies.value = a;
   const p = await getJSON("/api/profile");
   if (p && p.army && Array.isArray(p.army.group)) group.value = p.army.group.map(String);
  }
  onMounted(load);
  usePolling(async ()=>{ const a=await getJSON("/api/armies"); if(Array.isArray(a)) armies.value=a; }, 4000);

  const inGroup = (uid)=> group.value.includes(String(uid));
  function toggle(uid){
   uid = String(uid);
   group.value = inGroup(uid) ? group.value.filter(u=>u!==uid) : [...group.value, uid];
  }
  async function save(){
   saved.value = "";
   const r = await postJSON("/api/profile", { army: { group: group.value } });
   saved.value = (r && r.ok) ? "Đã lưu ✓" : "Lưu lỗi";
   // reflect what the server actually accepted (invalid uids are dropped)
   if (r && r.applied && r.applied.army && Array.isArray(r.applied.army.group))
     group.value = r.applied.army.group.map(String);
  }
  return { armies, group, saved, inGroup, toggle, save };
 },
 template:`<div class="card"><h2>Đội farm (nhóm nâng cấp / farm)</h2>
  <div class="kv" style="color:#8b949e;margin-bottom:8px">Chọn các đội là <b>đội farm</b>. Nâng-lính rút
   lính dưới cấp từ nhóm này để nâng; nếu không chọn đội nào, nâng-lính sẽ <b>không chạy</b>. (Tối đa 5 đội/ô.)</div>
  <div v-for="a in armies" :key="a.uid" style="display:flex;align-items:center;gap:8px;margin:3px 0">
   <label class="kv" style="display:flex;align-items:center;gap:6px;cursor:pointer">
    <input type="checkbox" :checked="inGroup(a.uid)" @change="toggle(a.uid)"/>
    <b>{{ a.name || a.uid }}</b>
    <span class="muted" style="font-size:12px">· {{ (a.pawns||[]).length }} lính · {{ a.state_label||"" }}</span>
   </label>
  </div>
  <div v-if="!armies.length" class="muted">(chưa có đội)</div>
  <div style="margin-top:8px">
   <button @click="save">Lưu đội farm ({{ group.length }})</button>
   <span class="kv" style="margin-left:10px;color:#199e70">{{ saved }}</span>
  </div></div>`
};
