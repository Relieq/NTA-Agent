import { getJSON, postJSON, usePolling } from "../api.js";
import Collapsible from "./Collapsible.js";
const { ref, onMounted } = window.Vue;

// Đội farm = profile.army.group: nhóm đội agent coi là "đội farm cố định". Nâng-lính
// rút lính dưới cấp TỪ nhóm này; occupy ưu tiên nhóm này. Không chọn -> nâng-lính đứng im.
export default {
 components:{ Collapsible },
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
  const byUid = (uid)=> armies.value.find(a=>String(a.uid)===String(uid));
  const nameOf = (uid)=> { const a=byUid(uid); return a ? (a.name||a.uid) : "(đội đã mất)"; };
  const names = ()=> group.value.map(nameOf).join(", ");
  // Order = the order armies enter a battle in 1-tile (the first goes in first) and the order
  // the dig evaluation simulates them in: move with ▲▼ or drag.
  function move(i, d){
   const j=i+d; if(j<0||j>=group.value.length) return;
   const g=group.value.slice(); [g[i],g[j]]=[g[j],g[i]]; group.value=g; saved.value="";
  }
  const dragFrom = ref(-1);
  function onDragStart(i){ dragFrom.value=i; }
  function onDragOver(i, ev){ ev.preventDefault(); }
  function onDrop(i){
   const f=dragFrom.value; dragFrom.value=-1; if(f<0||f===i) return;
   const g=group.value.slice(); const [x]=g.splice(f,1); g.splice(i,0,x); group.value=g; saved.value="";
  }
  return { armies, group, saved, inGroup, toggle, save, names, move, nameOf, byUid,
           dragFrom, onDragStart, onDragOver, onDrop };
 },
 template:`<div class="card"><h2>Đội farm (nhóm nâng cấp / farm)</h2>
  <div class="kv" style="color:#8b949e;margin-bottom:8px">Chọn các đội là <b>đội farm</b>. Nâng-lính rút
   lính dưới cấp từ nhóm này để nâng; nếu không chọn đội nào, nâng-lính sẽ <b>không chạy</b>. (Tối đa 5 đội/ô.)</div>
  <Collapsible id="farm-group" title="Chọn đội farm"
   :summary="group.length ? group.length+' đội: '+names() : 'chưa chọn đội nào'">
  <div v-for="a in armies" :key="a.uid" style="display:flex;align-items:center;gap:8px;margin:3px 0">
   <label class="kv" style="display:flex;align-items:center;gap:6px;cursor:pointer">
    <input type="checkbox" :checked="inGroup(a.uid)" @change="toggle(a.uid)"/>
    <b>{{ a.name || a.uid }}</b>
    <span class="muted" style="font-size:12px">· {{ (a.pawns||[]).length }} lính · {{ a.state_label||"" }}</span>
   </label>
  </div>
  <div v-if="!armies.length" class="muted">(chưa có đội)</div>
  <div v-if="group.length" style="margin-top:10px">
   <div class="kv" style="color:#8b949e;margin-bottom:4px">Thứ tự vào trận — đội <b>đầu tiên vào trước</b>
    (chế độ 1-tile; đánh giá đường dig cũng mô phỏng đúng thứ tự này). Kéo thả hoặc dùng ▲▼, rồi bấm Lưu.</div>
   <div v-for="(u,i) in group" :key="u" draggable="true"
     @dragstart="onDragStart(i)" @dragover="onDragOver(i,$event)" @drop="onDrop(i)"
     :style="{display:'flex',alignItems:'center',gap:'8px',margin:'3px 0',padding:'3px 8px',border:'1px solid var(--border-hi, #30363d)',borderRadius:'6px',cursor:'grab',opacity:dragFrom===i?0.5:1}">
    <span class="muted" style="width:1.5em;text-align:right">{{ i+1 }}.</span>
    <b>{{ nameOf(u) }}</b>
    <span class="muted" style="font-size:12px">· {{ ((byUid(u)||{}).pawns||[]).length }} lính</span>
    <span style="margin-left:auto">
     <button :disabled="i===0" @click="move(i,-1)" style="padding:0 6px">▲</button>
     <button :disabled="i===group.length-1" @click="move(i,1)" style="padding:0 6px">▼</button></span>
   </div>
  </div>
  <div style="margin-top:8px">
   <button @click="save">Lưu đội farm ({{ group.length }})</button>
   <span class="kv" style="margin-left:10px;color:#199e70">{{ saved }}</span>
  </div></Collapsible></div>`
};
