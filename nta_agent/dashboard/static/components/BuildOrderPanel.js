import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
export default {
 setup(){
  const rows=ref([]);   // [{id, name, skip}]
  const names=ref({}); const msg=ref(""); const dragId=ref(null);
  async function load(){
   const p=await getJSON("/api/profile"); if(!p) return;
   names.value=p.names||{};
   const b=p.build||{order:[],skip:[]};
   const skip=new Set((b.skip||[]).map(Number));
   const cat=(p.catalogue||[]).map(c=>c.id);
   const order=(b.order||[]).map(Number).filter(i=>cat.includes(i));
   const ids=order.concat(cat.filter(i=>!order.includes(i)));
   rows.value=ids.map(id=>({id, name:(names.value[id]||("#"+id)), skip:skip.has(id)}));
  }
  onMounted(load);
  const idxOf=id=>rows.value.findIndex(r=>r.id===id);
  function move(id,dir){ const i=idxOf(id), j=i+dir;
   if(i<0||j<0||j>=rows.value.length) return;
   const a=[...rows.value]; [a[i],a[j]]=[a[j],a[i]]; rows.value=a; }
  function onDragStart(id){ dragId.value=id; }
  function onDragOver(id,ev){ ev.preventDefault();
   if(dragId.value==null||dragId.value===id) return;
   const from=idxOf(dragId.value), to=idxOf(id);
   const a=[...rows.value]; const [m]=a.splice(from,1); a.splice(to,0,m); rows.value=a; }
  function onDragEnd(){ dragId.value=null; }
  async function save(){
   msg.value=" đang lưu…";
   const order=rows.value.map(r=>r.id);
   const skip=rows.value.filter(r=>r.skip).map(r=>r.id);
   const o=await postJSON("/api/profile",{order,skip});
   msg.value=(o&&o.ok)?" ✓ đã lưu":(" ⚠️ "+((o&&o.error)||"lỗi"));
   load();
  }
  return { rows, msg, dragId, move, onDragStart, onDragOver, onDragEnd, save };
 },
 template:`<div class="card full"><h2>Xây dựng — Thứ tự xây &amp; Bỏ qua</h2>
  <div class="muted">Kéo-thả hoặc ▲▼ để đổi ưu tiên; tick "bỏ qua" để agent không tự đụng.</div>
  <ul class="bolist">
   <li v-for="r in rows" :key="r.id" draggable="true" :class="{drag:dragId===r.id, skip:r.skip}"
    @dragstart="onDragStart(r.id)" @dragover="onDragOver(r.id,$event)" @dragend="onDragEnd">
    <span class="grip">⠿</span>
    <span class="nm">{{ r.name }} <span class="muted">({{ r.id }})</span></span>
    <button title="Lên" @click="move(r.id,-1)">▲</button>
    <button title="Xuống" @click="move(r.id,1)">▼</button>
    <label><input type="checkbox" v-model="r.skip"> bỏ qua</label>
   </li></ul>
  <button style="margin-top:6px" @click="save">Lưu thứ tự xây</button>
  <span class="muted">{{ msg }}</span></div>`
};
