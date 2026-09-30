const { ref } = window.Vue;
// A list that is COLLAPSED by default: a one-line header (title + summary of the
// current choice) you click to open. The open/closed state is remembered per `id` in
// localStorage, so a list you keep open stays open after a reload.
const KEY = "nta.open";
function load(){ try{ return JSON.parse(localStorage.getItem(KEY)) || {}; }catch(e){ return {}; } }
function save(m){ try{ localStorage.setItem(KEY, JSON.stringify(m)); }catch(e){} }
export default {
 props: { id: String, title: String, summary: String, badge: String, open: { type: Boolean, default: false } },
 setup(props){
  const isOpen = ref(props.id && props.id in load() ? !!load()[props.id] : props.open);
  function toggle(){
   isOpen.value = !isOpen.value;
   if(props.id){ const m = load(); m[props.id] = isOpen.value; save(m); }
  }
  return { isOpen, toggle };
 },
 template: `<div class="collapsible">
  <div @click="toggle" style="cursor:pointer;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;padding:2px 0">
   <span class="muted" style="width:10px">{{ isOpen ? "▾" : "▸" }}</span>
   <b>{{ title }}</b>
   <span v-if="badge" style="font-size:11px;padding:0 6px;border-radius:8px;border:1px solid #d29922;color:#d29922">{{ badge }}</span>
   <span v-if="summary" class="muted" style="font-size:12px">{{ summary }}</span></div>
  <div v-if="isOpen" style="margin:2px 0 6px 18px"><slot/></div></div>`
};
