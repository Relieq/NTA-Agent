import StatusHeader from "./StatusHeader.js";
import Sidebar from "./Sidebar.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
import ArmiesPanel from "./ArmiesPanel.js";
import DecisionsPanel from "./DecisionsPanel.js";
import EquipmentPanel from "./EquipmentPanel.js";
import TerritoryPanel from "./TerritoryPanel.js";
import FortsPanel from "./FortsPanel.js";
import BuildOrderPanel from "./BuildOrderPanel.js";
import BrainChatPanel from "./BrainChatPanel.js";
import EventsPanel from "./EventsPanel.js";
const { ref } = window.Vue;
const TABS=[
 {id:"overview", label:"Tổng quan", icon:"▦"},
 {id:"army",     label:"Quân đội",  icon:"⚔"},
 {id:"territory",label:"Lãnh thổ",  icon:"🗺"},
 {id:"build",    label:"Xây dựng & Chiến thuật", icon:"🛠"},
 {id:"log",      label:"Nhật ký",   icon:"📜"},
];
function loadTab(){ try{ return localStorage.getItem("nta.tab")||"overview"; }catch(e){ return "overview"; } }
export default {
 components:{ StatusHeader, Sidebar, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel,
  DecisionsPanel, EquipmentPanel, TerritoryPanel, FortsPanel, BuildOrderPanel, BrainChatPanel, EventsPanel },
 setup(){
  const activeTab=ref(loadTab());
  function select(id){ activeTab.value=id; try{ localStorage.setItem("nta.tab", id); }catch(e){} }
  return { TABS, activeTab, select };
 },
 template:`<div><StatusHeader/>
  <div class="shell">
   <Sidebar :tabs="TABS" :active="activeTab" @select="select"/>
   <main class="content">
    <div v-if="activeTab==='overview'" class="grid">
     <ResourcePanel/><CityPanel/><MiscPanel/></div>
    <div v-if="activeTab==='army'" class="grid">
     <ArmiesPanel/><DecisionsPanel/><EquipmentPanel/></div>
    <div v-show="activeTab==='territory'" class="grid">
     <TerritoryPanel/><FortsPanel/></div>
    <div v-if="activeTab==='build'" class="grid">
     <BuildOrderPanel/><BrainChatPanel/></div>
    <div v-if="activeTab==='log'" class="grid">
     <EventsPanel/></div>
   </main>
  </div></div>`
};
