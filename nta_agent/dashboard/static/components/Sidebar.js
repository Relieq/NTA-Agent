export default {
 props:{ tabs:Array, active:String },
 emits:["select"],
 template:`<nav class="sidebar">
  <button v-for="t in tabs" :key="t.id" class="tabbtn" :class="{on:t.id===active}"
    @click="$emit('select', t.id)" :title="t.label">
   <span class="ticon">{{ t.icon }}</span><span class="tlbl">{{ t.label }}</span></button>
 </nav>`
};
