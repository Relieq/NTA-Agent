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
  // server refusals of the agent's builds (issue #82) — so a silent stall is visible
  const rej=ref([]);
  const loadRej=async ()=>{ rej.value=(await getJSON("/api/build/rejections"))||[]; };
  onMounted(()=>{ loadRej(); setInterval(loadRej, 10000); });
  const ago=(ts)=>{ const s=Math.max(0,Math.round(Date.now()/1000-(ts||0)));
   return s<60? s+"s" : s<3600? Math.round(s/60)+"'" : Math.round(s/3600)+"h"; };
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
  return { rows, msg, dragId, move, onDragStart, onDragOver, onDragEnd, save, rej, ago };
 },
 template:`<div class="card full"><h2>Xây dựng — Thứ tự xây &amp; Bỏ qua</h2>
  <div class="muted">Kéo-thả hoặc ▲▼ để đổi ưu tiên; tick "bỏ qua" để agent không tự đụng.</div>
  <div v-if="rej.length" style="margin:6px 0;font-size:12px;border:1px solid #d29922;border-radius:6px;padding:6px">
   <b style="color:#d29922">Game từ chối xây gần đây</b> <span class="muted">(agent tự đồng bộ lại công trình từ game)</span>
   <div v-for="(r,i) in rej" :key="i">{{ ago(r.ts) }} trước · {{ r.kind==="construct" ? "xây" : "nâng" }} <b>{{ r.name }}</b>
    — ecode {{ r.ecode }}<span v-if="r.reason">: {{ r.reason }}</span></div></div>
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
